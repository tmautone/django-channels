from django.http import HttpResponse
from django.utils.six import PY3


def encode_response(response):
    """
    Encodes a response to JSON-compatible datastructures
    """
    value = {
        "content_type": getattr(response, "content_type", None),
        "content": response.content,
        "status": response.status_code,
        "headers": list(response._headers.values()),
        "cookies": [v.output(header="") for _, v in response.cookies.items()]
    }
    if PY3:
        value["content"] = value["content"].decode('utf8')
    response.close()
    return value


def decode_response(value):
    """
    Decodes a response JSONish value to a HttpResponse object.
    """
    response = HttpResponse(
        content=value['content'],
        content_type=value['content_type'],
        status=value['status'],
    )
    for cookie in value['cookies']:
        response.cookies.load(cookie)
    response._headers = {k.lower(): (k, v) for k, v in value['headers']}
    return response


class ResponseLater(Exception):
    """
    Class that represents a response which will be sent down the response
    channel later. Used to move a django view-based segment onto the next
    task, as otherwise we'd need to write some kind of fake response.
    """
    pass
