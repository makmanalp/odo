from __future__ import print_function, division, absolute_import

import os
import uuid

from contextlib import contextmanager, closing

try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen

from toolz import memoize
from toolz.curried import take, map, pipe

from .. import discover
from ..resource import resource
from ..append import append
from ..convert import convert
from ..temp import Temp, _Temp
from .csv import CSV
from .json import JSON, JSONLines
from .text import TextFile


from multipledispatch import MDNotImplementedError

from .text import TextFile

from ..compatibility import urlparse
from ..utils import tmpfile, ext, sample, filter_kwargs


class _URL(object):
    """ Parent class for data accessed through ``URLs``

    Parameters
    ----------

    url : str
        full url to file
    chunk_size : int (default 1024)
        Size of chunks streamed into memory
    decode_unicode : bool (default False)
        If True, content will be decoded using the best available encoding based on the response.

     Examples
    --------

    >>> from odo import URL, CSV
    >>> u = URL(CSV)('http://foo.com/myfile.csv')

    Normally create through resource uris

    >>> data = resource('http://foo.com/myfile.csv')
    >>> data.url
    'http://foo.com/myfile.csv'
    >>> data.filename
    'myfile.csv'
    """
    def __init__(self, url, chunk_size=1024, decode_unicode=False, *args,
                 **kwargs):

        self.subtype.__init__(self, url, *args, **kwargs)

        self.url = url
        self.chunk_size = chunk_size
        self.decode_unicode = decode_unicode
        self.filename = os.path.basename(urlparse(url).path)


def URL(cls):
    return type('URL(%s)' % cls.__name__, (_URL, cls), {'subtype': cls})

URL.__doc__ = _URL.__doc__
URL = memoize(URL)

@sample.register((URL(CSV), URL(JSONLines)))
@contextmanager
def sample_url_line_delimited(data, lines=5):
    """Get a size `length` sample from an URL CSV or URL line-delimited JSON.

    Parameters
    ----------
    data : URL(CSV)
        A hosted CSV
    lines : int, optional, default ``8192``
        Number of bytes to read into memory
    """

    with closing(urlopen(data.url)) as r:

        raw = pipe(r, map(bytes.decode), take(10), list, '\n'.join)
        with tmpfile(data.filename) as fn:
            with open(fn, 'wb') as f:
                f.write(raw)
            yield fn


@discover.register((URL(CSV), URL(JSONLines)))
def discover_url_line_delimited(c, lines=5, **kwargs):
    """Discover CSV and JSONLines files from URL."""
    with sample(c, lines=lines) as fn:
        return discover(c.subtype(fn, **kwargs), **kwargs)

types_by_extension = {'csv': CSV, 'json': JSONLines, 'txt': TextFile}

@resource.register('ftp://.+', priority=16)
@resource.register('http://.+', priority=16)
@resource.register('https://.+', priority=16)
def resource_url(uri, **kwargs):
    path = os.path.basename(urlparse(uri).path)
    try:
        subtype = types_by_extension[ext(path)]
    except KeyError:
        subtype = type(resource(path))

    return URL(subtype)(uri, **kwargs)


@append.register(TextFile, URL(TextFile))
@append.register(JSONLines, URL(JSONLines))
@append.register(JSON, URL(JSON))
@append.register(CSV, URL(CSV))
def append_urlX_to_X(target, source, **kwargs):

    with closing(urlopen(source.url)) as r:
        chunk_size = 16 * source.chunk_size
        with open(target.path, 'wb') as fp:
          while True:
            chunk = r.read(chunk_size)
            if not chunk: break
            fp.write(chunk)

    return target

@convert.register(Temp(TextFile), (Temp(URL(TextFile)), URL(TextFile)))
@convert.register(Temp(JSONLines), (Temp(URL(JSONLines)), URL(JSONLines)))
@convert.register(Temp(JSON), (Temp(URL(JSON)), URL(JSON)))
@convert.register(Temp(CSV), (Temp(URL(CSV)), URL(CSV)))
def url_file_to_temp_file(data, **kwargs):
    fn = '.%s' % uuid.uuid1()
    target = Temp(data.subtype)(fn, **kwargs)
    return append(target, data, **kwargs)


@convert.register(Temp(URL(TextFile)), (TextFile, Temp(TextFile)))
@convert.register(Temp(URL(JSONLines)), (JSONLines, Temp(JSONLines)))
@convert.register(Temp(URL(JSON)), (JSON, Temp(JSON)))
@convert.register(Temp(URL(CSV)), (CSV, Temp(CSV)))
def file_to_temp_ssh_file(data, **kwargs):
    fn = '%s' % uuid.uuid1()
    if isinstance(data, _Temp):
        target = Temp(URL(data.persistent_type))(fn, **kwargs)
    else:
        target = Temp(URL(type(data)))(fn, **kwargs)
    return append(target, data, **kwargs)

try:
    from .hdfs import HDFS
    from .aws import S3
except ImportError:
    pass
else:
    @append.register(HDFS(JSON), URL(JSON))
    @append.register(HDFS(TextFile), URL(TextFile))
    @append.register(HDFS(TextFile), URL(TextFile))
    @append.register(S3(JSONLines), URL(JSONLines))
    @append.register(HDFS(JSONLines), URL(JSONLines))
    @append.register(HDFS(JSONLines), URL(JSONLines))
    @append.register(HDFS(JSON), URL(JSON))
    @append.register(HDFS(CSV), URL(CSV))
    @append.register(HDFS(CSV), URL(CSV))
    @append.register(S3(TextFile), URL(TextFile))
    @append.register(S3(JSON), URL(JSON))
    @append.register(S3(CSV), URL(CSV))
    def other_remote_text_to_url_text(a, b, **kwargs):
        raise MDNotImplementedError()

