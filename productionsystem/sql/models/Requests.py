"""Requests Table."""
import json
import logging
from contextlib import contextmanager
from datetime import datetime

import cherrypy
from sqlalchemy import Column, Integer, TIMESTAMP, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from productionsystem.apache_utils import check_credentials, admin_only, dummy_credentials
from ..utils import db_session
from ..enums import LocalStatus
from ..registry import managed_session
from ..JSONTableEncoder import JSONTableEncoder
from .SQLTableBase import SQLTableBase
from .Users import Users
from .ParametricJobs import ParametricJobs


def json_handler(*args, **kwargs):
    """Handle JSON encoding of response."""
    value = cherrypy.serving.request._json_inner_handler(*args, **kwargs)
    return json.dumps(value, cls=JSONTableEncoder)


def subdict(dct, keys):
    """Create a sub dictionary."""
    return {k: dct[k] for k in keys if k in dct}


@cherrypy.expose
@cherrypy.popargs('request_id')
class Requests(SQLTableBase):
    """Requests SQL Table."""

    __tablename__ = 'requests'
    id = Column(Integer, primary_key=True)  # pylint: disable=invalid-name
    requester_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    request_date = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    status = Column(Enum(LocalStatus), nullable=False, default=LocalStatus.REQUESTED)
    timestamp = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    parametric_jobs = relationship("ParametricJobs", back_populates="request", cascade="all, delete-orphan")
    logger = logging.getLogger(__name__)

    def submit(self):
        """Submit Request."""
        with db_session() as session:
            parametricjobs = session.query(ParametricJobs).filter_by(request_id=self.id).all()
            session.expunge_all()
            session.merge(self).status = LocalStatus.SUBMITTING

        self.logger.info("Submitting request %s", self.id)

        submitted_jobs = []
        try:
            for job in parametricjobs:
                job.submit()
                submitted_jobs.append(job)
        except:
            self.logger.exception("Exception while submitting request %s", self.id)
            self.logger.info("Resetting associated ParametricJobs")
            for job in submitted_jobs:
                job.reset()


    def update_status(self):
        """Update request status."""
        with db_session() as session:
            parametricjobs = session.query(ParametricJobs).filter_by(request_id=self.id).all()
            session.expunge_all()

        statuses = []
        for job in parametricjobs:
            try:
                statuses.append(job.update_status())
            except:
                self.logger.exception("Exception updating ParametricJob %s", job.id)

        status = max(statuses or [self.status])
        if status != self.status:
            with db_session(reraise=False) as session:
                session.merge(self).status = status
            self.logger.info("Request %s moved to state %s", self.id, status.name)

    @classmethod
    @cherrypy.tools.accept(media='application/json')
    @cherrypy.tools.json_out(handler=json_handler)
    @dummy_credentials
#    @check_credentials
    def GET(cls, request_id=None):  # pylint: disable=invalid-name
        """REST Get method."""
        cls.logger.debug("In GET: reqid = %r", request_id)
        requester = cherrypy.request.verified_user
        with managed_session() as session:
            query = session.query(cls, Users)
            if not requester.admin:
                query = session.query(cls)
                query = query.filter_by(requester_id=requester.id)

            if request_id is not None:
                with cherrypy.HTTPError.handle(ValueError, 400, 'Bad request_id: %r' % request_id):
                    request_id = int(request_id)
                query = query.filter_by(id=request_id)

            if requester.admin:
                return [dict(request, requester=user.name, status=request.status.name)
                        for request, user in query.join(Users, cls.requester_id == Users.id).all()]
            return query.all()


    @classmethod
    @check_credentials
    @admin_only
    def DELETE(cls, request_id):  # pylint: disable=invalid-name
        """REST Delete method."""
        cls.logger.info("Deleting Request id: %s", request_id)
#        if not cherrypy.request.verified_user.admin:
#            raise cherrypy.HTTPError(401, "Unauthorised")
        with cherrypy.HTTPError.handle(ValueError, 400, 'Bad request_id: %r' % request_id):
            request_id = int(request_id)
        with managed_session() as session:
            try:
                #  request = session.query(Requests).filter_by(id=request_id).delete()
                request = session.query(cls).filter_by(id=request_id).one()
            except NoResultFound:
                message = "No Request found with id: %s" % request_id
                cls.logger.warning(message)
                raise cherrypy.NotFound(message)
            except MultipleResultsFound:
                message = "Multiple Requests found with id: %s!" % request_id
                cls.logger.error(message)
                raise cherrypy.HTTPError(500, message)
            session.delete(request)

    @classmethod
    @check_credentials
    @admin_only
    def PUT(cls, request_id, status):  # pylint: disable=invalid-name
        """REST Put method."""
        cls.logger.debug("In PUT: reqid = %s, status = %s", request_id, status)
#        if not cherrypy.request.verified_user.admin:
#            raise cherrypy.HTTPError(401, "Unauthorised")
        with cherrypy.HTTPError.handle(ValueError, 400, 'Bad request_id: %r' % request_id):
            request_id = int(request_id)
        if status.upper() not in LocalStatus.members_names():
            raise cherrypy.HTTPError(400, "bad status")

        with managed_session() as session:
            try:
                request = session.query(cls).filter_by(id=request_id).one()
            except NoResultFound:
                message = "No Request found with id: %s" % request_id
                cls.logger.warning(message)
                raise cherrypy.NotFound(message)
            except MultipleResultsFound:
                message = "Multiple Requests found with id: %s!" % request_id
                cls.logger.error(message)
                raise cherrypy.HTTPError(500, message)

            request.status = LocalStatus[status.upper()]

    @classmethod
    @cherrypy.tools.json_in()
    @check_credentials
    def POST(cls):  # pylint: disable=invalid-name
        """REST Post method."""
        data = cherrypy.request.json
        cls.logger.debug("In POST: kwargs = %s", data)

        request = cls(requester_id=cherrypy.request.verified_user.id)
        request.parametric_jobs = []
        for job in data:
            request.parametric_jobs.append(ParametricJobs(**subdict(job,
                                                                    ('allowed'))))
        with managed_session() as session:
            session.add(request)

# Have to add this after class is defined as ParametricJobs SQL setup requires it to be defined.
Requests.parametricjobs = ParametricJobs()