import threading

from django.core.management.commands.runserver import \
    Command as RunserverCommand

from channels import DEFAULT_CHANNEL_BACKEND, channel_backends
from channels.adapters import UrlConsumer
from channels.interfaces.wsgi import WSGIInterface
from channels.log import setup_logger
from channels.worker import Worker


class Command(RunserverCommand):

    def handle(self, *args, **options):
        self.verbosity = options.get("verbosity", 1)
        self.logger = setup_logger('django.channels', self.verbosity)
        super(Command, self).handle(*args, **options)

    def get_handler(self, *args, **options):
        """
        Returns the default WSGI handler for the runner.
        """
        return WSGIInterface(self.channel_backend)

    def run(self, *args, **options):
        # Run the rest
        return super(Command, self).run(*args, **options)

    def inner_run(self, *args, **options):
        # Check a handler is registered for http reqs
        self.channel_backend = channel_backends[DEFAULT_CHANNEL_BACKEND]
        if not self.channel_backend.registry.consumer_for_channel("http.request"):
            # Register the default one
            self.channel_backend.registry.add_consumer(UrlConsumer(), ["http.request"])
        # Note that this is the right one on the console
        self.logger.info("Worker thread running, channels enabled")
        if self.channel_backend.local_only:
            self.logger.info("Local channel backend detected, no remote channels support")
        # Launch a worker thread
        worker = WorkerThread(self.channel_backend)
        worker.daemon = True
        worker.start()
        # Run rest of inner run
        super(Command, self).inner_run(*args, **options)


class WorkerThread(threading.Thread):
    """
    Class that runs a worker
    """

    def __init__(self, channel_backend):
        super(WorkerThread, self).__init__()
        self.channel_backend = channel_backend

    def run(self):
        Worker(channel_backend=self.channel_backend).run()
