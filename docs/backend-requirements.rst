Channel Backend Requirements
============================

While the channel backends are pluggable, there's a minimum standard they
must meet in terms of the way they perform.

In particular, a channel backend MUST:

* Provide a ``send()`` method which sends a message onto a named channel

* Provide a ``receive_many()`` method which returns an available message on the
  provided channels, or returns no message either instantly or after a short
  delay (it must not block indefinitely)

* Provide a ``group_add()`` method which adds a channel to a named group
  for at least the provided expiry period.

* Provide a ``group_discard()`` method with removes a channel from a named
  group if it was added, and nothing otherwise.

* Provide a ``group_members()`` method which returns an iterable of all
  channels currently in the group.

* Preserve the ordering of messages inside a channel

* Never deliver a message more than once

* Never block on sending of a message (dropping the message/erroring is preferable to blocking)

* Be able to store messages of at least 5MB in size

* Expire messages only after the expiry period provided is up (a backend may
  keep them longer if it wishes, but should expire them at some reasonable
  point to ensure users do not come to rely on permanent messages)

In addition, it SHOULD:

* Provide a ``receive_many_blocking()`` method which is like ``receive_many()``
  but blocks until a message is available.

* Provide a ``send_group()`` method which sends a message to every channel
  in a group.

* Try and preserve a rough global ordering, so that one busy channel does not
  drown out an old message in another channel if a worker is listening on both.

