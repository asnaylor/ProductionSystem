"""Dirac Jobs Table."""
import logging
import json

import cherrypy
from sqlalchemy import Column, Integer, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from productionsystem.sql.registry import managed_session
from productionsystem.apache_utils import check_credentials, dummy_credentials
from ..enums import DiracStatus
from ..SQLTableBase import SQLTableBase


@cherrypy.expose
@cherrypy.popargs('diracjob_id')
class DiracJobs(SQLTableBase):
    """Dirac Jobs SQL Table."""

    __tablename__ = 'diracjobs'
    id = Column(Integer, primary_key=True)  # pylint: disable=invalid-name
    parametricjob_id = Column(Integer, ForeignKey('parametricjobs.id'), nullable=False)
    status = Column(Enum(DiracStatus), nullable=False, default=DiracStatus.UNKNOWN)
    reschedules = Column(Integer, nullable=False, default=0)
    parametricjob = relationship("ParametricJobs", back_populates='dirac_jobs')
    logger = logging.getLogger(__name__)

    @classmethod
    def get(cls, diracjob_id=None, request_id=None, parametricjob_id=None, user_id=None):
        """Get dirac jobs."""
        if diracjob_id is not None:
            try:
                diracjob_id = int(diracjob_id)
            except ValueError:
                cls.logger.error("Dirac job id: %r should be of type int "
                                 "(or convertable to int)", diracjob_id)
                raise

        if parametricjob_id is not None:
            try:
                parametricjob_id = int(parametricjob_id)
            except ValueError:
                cls.logger.error("Parametric job id: %r should be of type int "
                                 "(or convertable to int)", parametricjob_id)
                raise

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
            if diracjob_id is not None:
                query = query.filter_by(id=diracjob_id)
            if parametricjob_id is not None or request_id is not None or user_id is not None:
                query = query.join(cls.parametricjob)
                if parametricjob_id is not None:
                    query = query.filter_by(id=parametricjob_id)
                if request_id is not None:
                    query = query.filter_by(request_id=request_id)
                if user_id is not None:
                    query = query.join(cls.parametricjob.request).filter_by(requester_id=user_id)

            if diracjob_id is None:
                requests = query.all()
                session.expunge_all()
                return requests

            try:
                diracjob = query.one()
            except NoResultFound:
                cls.logger.warning("No result found for dirac job id: %d", diracjob_id)
                raise
            except MultipleResultsFound:
                cls.logger.error("Multiple results found for dirac job id: %d",
                                 parametricjob_id)
                raise
            session.expunge(diracjob)
            return diracjob
