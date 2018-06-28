"""SQLAlchemy Base Table Module."""
import json
from enum import Enum
from datetime import datetime
from abc import ABCMeta
from collections import Mapping
from sqlalchemy import Column
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.declarative.api import DeclarativeMeta

__all__ = ('SQLTableBase', )


class DeclarativeABCMeta(DeclarativeMeta, ABCMeta):
    """
    Declarative abstract base metaclass.

    Metaclass combining the SQLAlchemy DeclarativeMeta
    with the ABCMeta giving us the ability to use abstract
    decorators etc.
    """

    pass


class SmartColumn(Column):
    def __init__(self, *args, **kwargs):
        required = kwargs.pop('required', False)
        allowed = kwargs.pop('allowed', False)
        Column.__init__(self, *args, **kwargs)
        self._required = required
        self._allowed = required or allowed
    @property
    def required(self):
        return self._required
    @property
    def allowed(self):
        return self._allowed


class ColumnsDescriptor(object):
    """Yield the column names."""
    def __init__(self, required=False, allowed=False):
        self._required = required
        self._allowed = allowed
    def __get__(self, obj, cls):
        """Descriptor get."""
        for column in cls.__table__.columns:
            if self._required and not getattr(column, 'required', False):  # use getattr so works on normal column as well as smart column
                continue
            if self._allowed and not getattr(column, 'allowed', False):
                continue
            yield column.name

    def __set__(self, obj, value):
        """Descriptor set."""
        raise AttributeError("Read only attribute!")


class IterableBase(Mapping):
    """
    Iterable base class.

    A base class that provides the functionality of
    being able to iterate over the instrumented attributes
    of an SQLAlchemy declarative base.
    """

    # This we can get from the class as well as instance
    # unlike property
    columns = ColumnsDescriptor()
    required_columns = ColumnsDescriptor(required=True)
    allowed_columns = ColumnsDescriptor(allowed=True)

    def __iter__(self):
        """Get an iterator over instrumented attributes."""
        return self.columns

    def __getitem__(self, item):
        """Access instrumented attributes as a dict."""
        if item not in self.columns:
            raise KeyError("Invalid attribute name: %s" % item)
        return getattr(self, item, None)

    def __len__(self):
        return len(list(self.columns))

    def jsonable(self):
        """Return an easily JSON encodable object."""
        output_obj = {}
        for column, value in dict(self).iteritems():
            val = value
            if isinstance(value, Enum):
                val = value.name.capitalize()
            elif isinstance(value, datetime):
                val = value.isoformat(' ')
            output_obj[column] = val
        return output_obj

    def to_json(self):
        """Return a JSON representation of the object."""
        return json.dumps(self.jsonable())

    @classmethod
    def unsafe_construct(cls, *args, **kwargs):
        new = cls.__new__(cls, *args, **kwargs)
        super(IterableBase, new).__init__(*args, **kwargs)
#           super(cls, new).__init__(*args, **kwargs)
        return new


SQLTableBase = declarative_base(cls=IterableBase,  # pylint: disable=invalid-name
                                metaclass=DeclarativeABCMeta)
