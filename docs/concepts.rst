Concepts
========

Django's traditional view of the world revolves around requests and responses;
a request comes in, Django is fired up to serve it, generates a response to
send, and then Django goes away and waits for the next request.

That was fine when the internet was all driven by simple browser interactions,
but the modern Web includes things like WebSockets and HTTP2 server push,
which allow websites to communicate outside of this traditional cycle.

And, beyond that, there are plenty of non-critical tasks that applications
could easily offload until after a response as been sent - like saving things
into a cache, or thumbnailing newly-uploaded images.

Channels changes the way Django runs to be "event oriented" - rather than 
just responding to requests, instead Django responses to a wide array of events
sent on *channels*. There's still no persistent state - each event handler,
or *consumer* as we call them, is called independently in a way much like a
view is called.

Let's look at what *channels* are first.

What is a channel?
------------------

The core of Channels is, unsurprisingly, a datastructure called a *channel*.
What is a channel? It is an *ordered*, *first-in first-out queue* with
*message expiry* and *at-most-once delivery* to *only one listener at a time*.

You can think of it as analagous to a task queue - messages are put onto
the channel by *producers*, and then given to just one of the *consumers*
listening to that channnel.

By *at-most-once* we say that either one consumer gets the message or nobody
does (if the channel implementation crashes, let's say). The
alternative is *at-least-once*, where normally one consumer gets the message
but when things crash it's sent to more than one, which is not the trade-off
we want.

There are a couple of other limitations - messages must be JSON-serialisable,
and not be more than 1MB in size - but these are to make the whole thing
practical, and not too important to think about up front.

The channels have capacity, so a load of producers can write lots of messages
into a channel with no consumers and then a consumer can come along later and
will start getting served those queued messages.

If you've used channels in Go, these are reasonably similar to those. The key
difference is that these channels are network-transparent; the implementations
of channels we provide are all accessible across a network to consumers
and producers running in different processes or on different machines.

Inside a network, we identify channels uniquely by a name string - you can
send to any named channel from any machine connected to the same channel 
backend. If two different machines both write to the ``django.wsgi.request``
channel, they're writing into the same channel.

How do we use channels?
-----------------------

That's what a channel is, but how is Django using them? Well, inside Django
you can connect a function to consume a channel, like so::

    from channels.decorators import consumer

    @consumer("channel-name")
    def my_consumer(something, **kwargs):
        pass

This means that for every message on the channel, Django will call that
consumer function with the message as keyword arguments (messages are always
a dict, and are mapped to keyword arguments for send/receive).

Django can do this as rather than run in a request-response mode, Channels
changes Django so that it runs in a worker mode - it listens on all channels
that have consumers declared, and when a message arrives on one, runs the
relevant consumer.

In fact, this is illustrative of the new way Django runs to enable Channels to
work. Rather than running in just a single process tied to a WSGI server,
Django runs in three separate layers:

* Interface servers, which communicate between Django and the outside world.
  This includes a WSGI adapter as well as a separate WebSocket server - we'll
  cover this later.

* The channel backend, which is a combination of pluggable Python code and
  a datastore (a database, or Redis) and responsible for transporting messages.

* The workers, that listen on all relevant channels and run consumer code
  when a message is ready.

This may seem quite simplistic, but that's part of the design; rather than
try and have a full asynchronous architecture, we're just introducing a
slightly more complex abstraction than that presented by Django views.

A view takes a request and returns a response; a consumer takes a channel
message and can write out zero to many other channel messages.

Now, let's make a channel for requests (called ``django.wsgi.request``), 
and a channel per client for responses (e.g. ``django.wsgi.response.o4F2h2Fd``),
with the response channel a property (``send_channel``) of the request message.
Suddenly, a view is merely another example of a consumer::

    @consumer("django.wsgi.request")
    def my_consumer(send_channel, **request_data):
        # Decode the request from JSON-compat to a full object
        django_request = Request.decode(request_data)
        # Run view
        django_response = view(django_request)
        # Encode the response into JSON-compat format
        Channel(send_channel).send(django_response.encode())

In fact, this is how Channels works. The interface servers transform connections
from the outside world (HTTP, WebSockets, etc.) into messages on channels,
and then you write workers to handle these messages.

This may seem like it's still not very well designed to handle push-style
code - where you use HTTP2's server-sent events or a WebSocket to notify
clients of changes in real time (messages in a chat, perhaps, or live updates
in an admin as another user edits something).

However, the key here is that you can run code (and so send on channels) in
response to any event - and that includes ones you create. You can trigger
on model saves, on other incoming messages, or from code paths inside views
and forms.

.. _channel-types:

Channel Types
-------------

Now, if you think about it, there are actually two major uses for channels in
this model. The first, and more obvious one, is the dispatching of work to
consumers - a message gets added to a channel, and then any one of the workers
can pick it up and run the consumer.

The second kind of channel, however, is used for responses. Notably, these only
have one thing listening on them - the interface server. Each response channel
is individually named and has to be routed back to the interface server where
its client is terminated.

This is not a massive difference - they both still behave according to the core
definition of a *channel* - but presents some problems when we're looking to
scale things up. We can happily randomly load-balance normal channels across
clusters of channel servers and workers - after all, any worker can process
the message - but response channels would have to have their messages sent
to the channel server they're listening on.

For this reason, Channels treats these as two different *channel types*, and
denotes a *response channel* by having the first character of the channel name
be the character ``!`` - e.g. ``!django.wsgi.response.f5G3fE21f``. *Normal
channels* have no special prefix, but along with the rest of the response
channel name, they must contain only the characters ``a-z A-Z 0-9 - _``,
and be less than 200 characters long.

It's optional for a backend implementation to understand this - after all,
it's only important at scale, where you want to shard the two types differently
- but it's present nonetheless. For more on scaling, and how to handle channel
types if you're writing a backend or interface server, read :doc:`scaling`.

Groups
------

Because channels only deliver to a single listener, they can't do broadcast;
if you want to send a message to an arbitrary group of clients, you need to
keep track of which response channels of those you wish to send to.

Say I had a live blog where I wanted to push out updates whenever a new post is
saved, I would register a handler for the ``post_save`` signal and keep a
set of channels (here, using Redis) to send updates to::

    
    redis_conn = redis.Redis("localhost", 6379)

    @receiver(post_save, sender=BlogUpdate)
    def send_update(sender, instance, **kwargs):
        # Loop through all response channels and send the update
        for send_channel in redis_conn.smembers("readers"):
            Channel(send_channel).send(
                id=instance.id,
                content=instance.content,
            )

    @consumer("django.websocket.connect")
    def ws_connect(path, send_channel, **kwargs):
        # Add to reader set
        redis_conn.sadd("readers", send_channel)

While this will work, there's a small problem - we never remove people from
the ``readers`` set when they disconnect. We could add a consumer that
listens to ``django.websocket.disconnect`` to do that, but we'd also need to
have some kind of expiry in case an interface server is forced to quit or
loses power before it can send disconnect signals - your code will never
see any disconnect notification but the response channel is completely
invalid and messages you send there will never get consumed and just expire.

Because the basic design of channels is stateless, the channel server has no
concept of "closing" a channel if an interface server goes away - after all,
channels are meant to hold messages until a consumer comes along (and some
types of interface server, e.g. an SMS gateway, could theoretically serve
any client from any interface server).

That means that we need to follow a keepalive model, where the interface server
(or, if you want even better accuracy, the client browser/connection) sends
a periodic message saying it's still connected (though only for persistent
connection types like WebSockets; normal HTTP doesn't need this as it won't
stay connected for more than its own timeout).

Now, we could go back into our example above and add an expiring set and keep
track of expiry times and so forth, but this is such a common pattern that
we don't need to; Channels has it built in, as a feature called Groups::

    @receiver(post_save, sender=BlogUpdate)
    def send_update(sender, instance, **kwargs):
        Group("liveblog").send(
            id=instance.id,
            content=instance.content,
        )

    @consumer("django.websocket.connect")
    @consumer("django.websocket.keepalive")
    def ws_connect(path, send_channel, **kwargs):
        # Add to reader group
        Group("liveblog").add(send_channel)

Not only do groups have their own ``send()`` method (which backends can provide
an efficient implementation of), they also automatically manage expiry of 
the group members. You'll have to re-call ``Group.add()`` every so often to
keep existing members from expiring, but that's easy, and can be done in the
same handler for both ``connect`` and ``keepalive``, as you can see above.

Groups are generally only useful for response channels (ones starting with
the character ``!``), as these are unique-per-client.

Next Steps
----------

That's the high-level overview of channels and groups, and how you should
starting thinking about them - remember, Django provides some channels
but you're free to make and consume your own, and all channels are
network-transparent.

One thing channels are not, however, is guaranteed delivery. If you want tasks
you're sure will complete, use a system designed for this with retries and
persistence like Celery, or you'll need to make a management command that
checks for completion and re-submits a message to the channel if nothing
is completed (rolling your own retry logic, essentially).

We'll cover more about what kind of tasks fit well into Channels in the rest
of the documentation, but for now, let's progress to :doc:`getting-started`
and writing some code.
