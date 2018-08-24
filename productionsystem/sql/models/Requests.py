"""Requests Table."""
import json
import logging
from datetime import datetime

import cherrypy
from sqlalchemy import Column, Integer, TIMESTAMP, TEXT, ForeignKey, Enum
from sqlalchemy.orm import relationship, joinedload
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from productionsystem.apache_utils import check_credentials, admin_only, dummy_credentials
from ..enums import LocalStatus
from ..registry import managed_session
from ..SQLTableBase import SQLTableBase, SmartColumn
from ..models import ParametricJobs
from .Users import Users
#from .ParametricJobs import ParametricJobs


def subdict(dct, keys, **kwargs):
    """Create a sub dictionary."""
    out = {k: dct[k] for k in keys if k in dct}
    out.update(kwargs)
    return out


@cherrypy.expose
@cherrypy.popargs('request_id')
class Requests(SQLTableBase):
    """Requests SQL Table."""

    __tablename__ = 'requests'
    classtype = Column(TEXT)
    __mapper_args__ = {'polymorphic_on': classtype,
                       'polymorphic_identity': 'requests'}
    id = Column(Integer, primary_key=True)  # pylint: disable=invalid-name
    description = SmartColumn(TEXT, nullable=True, allowed=True)
    requester_id = SmartColumn(Integer, ForeignKey('users.id'), nullable=False, required=True)
    request_date = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    status = Column(Enum(LocalStatus), nullable=False, default=LocalStatus.REQUESTED)
    timestamp = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    parametric_jobs = relationship("ParametricJobs", back_populates="request", cascade="all, delete-orphan")
    requester = relationship("Users")
    logger = logging.getLogger(__name__)

    def __init__(self, **kwargs):
        required_args = set(self.required_columns).difference(kwargs)
        if required_args:
            raise ValueError("Missing required keyword args: %s" % list(required_args))
        super(Requests, self).__init__(**subdict(kwargs, self.allowed_columns))
        parametricjobs = kwargs.get('parametricjobs', [])
        if not parametricjobs:
            self.logger.warning("No parametricjobs associated with new request.")
        for parametricjob in parametricjobs:
            parametricjob.pop('request_id', None)
            try:
                self.parametric_jobs.append(ParametricJobs(request_id=self.id, **parametricjob))
            except ValueError:
                self.logger.exception("Error creating parametricjob, bad input: %s", parametricjob)
                raise

    def add(self):
        with managed_session() as session:
            session.add(self)
            session.flush()
            session.refresh(self)

    def submit(self):
        """Submit Request."""
        self.logger.info("Submitting request %s", self.id)
        try:
            for job in self.parametric_jobs:
                job.submit()
        except:
            self.logger.exception("Exception while submitting request %s", self.id)
            raise

    def update_status(self):
        """Update request status."""
        if not self.parametric_jobs:
            self.logger.warning("No parametric jobs associated with request: %d. returning status unknown", self.id)
            self.status = LocalStatus.UNKNOWN
            return

        statuses = []
        for job in self.parametric_jobs:
            try:
                job.update_status()
            except:
                self.logger.exception("Exception updating ParametricJob %s", job.id)
            statuses.append(job.status)

        status = max(statuses)
        if status != self.status:
            self.status = status
            self.logger.info("Request %d moved to state %s", self.id, status.name)

    @staticmethod
    def _datatable_format_headers():
        columns = [{"data": "id", "title": "ID", "className": "rowid", "width": "5%"},
                   {"data": "description", "title": "Description", "width": "80%"},
                   {"data": "status", "title": "Status", "width": "7.5%"},
                   {"data": "request_date", "title": "Request Date", "width": "7.5%"}]
        if cherrypy.request.verified_user.admin:
            columns[2]['width'] = "70%"
            columns.append({"data": "requester", "title": "Requester", "width": "10%"})

        cherrypy.response.headers['Datatable-Order'] = json.dumps([[1, "desc"]])
        cherrypy.response.headers["Datatable-Columns"] = json.dumps(columns)

    @classmethod
    def delete(cls, request_id):
        try:
            request_id = int(request_id)
        except ValueError:
            cls.logger.error("Request id: %r should be of type int "
                             "(or convertable to int)", request_id)
            raise

        with managed_session() as session:
            try:
                request = session.query(cls).filter_by(id=request_id).one()
            except NoResultFound:
                cls.logger.warning("No result found for request id: %d", request_id)
                raise
            except MultipleResultsFound:
                cls.logger.error("Multiple results found for request id: %d", request_id)
                raise
            session.delete(request)
            cls.logger.info("Request %d deleted.", request_id)

    @classmethod
    def get(cls, request_id=None, user_id=None, load_user=False):
        """Get requests."""
        if request_id is not None:
            try:
                request_id = int(request_id)
            except ValueError:
                cls.logger.error("Request id: %r should be of type int "
                                 "(or convertable to int)", request_id)
                raise

        if user_id is not None:
            try:
                user_id = int(user_id)
            except ValueError:
                cls.logger.error("User id: %r should be of type int "
                                 "(or convertable to int)", user_id)
                raise

        with managed_session() as session:
            query = session.query(cls)
            if load_user:
                query = query.options(joinedload(cls.requester, innerjoin=True))
            if user_id is not None:
                query = query.filter_by(requester_id=user_id)

            if request_id is None:
                requests = query.all()
                session.expunge_all()
                return requests

            try:
                request = query.filter_by(id=request_id).one()
            except NoResultFound:
                cls.logger.warning("No result found for request id: %d", request_id)
                raise
            except MultipleResultsFound:
                cls.logger.error("Multiple results found for request id: %d", request_id)
                raise
            # Need the all if loading the user db object as well.
            # If not then doesn't hurt as only one object this session
            session.expunge_all()
            return request

    @classmethod
#    @check_credentials
#    @admin_only
    @dummy_credentials
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
            cls.logger.info("Request %d changed to status %s", request_id, status.upper())
