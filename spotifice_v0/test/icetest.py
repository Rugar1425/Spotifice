import logging
import socket
import time
from functools import cached_property
from threading import Thread
from unittest import TestCase

import Ice
import IceStorm


def ice_initialize_with_props(props_dict):
    init_data = Ice.InitializationData()
    init_data.properties = Ice.createProperties()
    for k, v in props_dict.items():
        init_data.properties.setProperty(k, v)

    return Ice.initialize(init_data)


class ThreadIceServer:
    def __init__(self, main, props, *args):
        self.ic = ice_initialize_with_props(props)
        self.thread = Thread(target=main, args=(self.ic,) + args)
        self.thread.start()

    def shutdown(self):
        if not self.ic:
            return

        self.ic.shutdown()

        self.thread.join(3)
        if self.thread.is_alive():
            logging.warning("Thread could not be joined in time")

        self.ic.destroy()
        self.ic = None


class IceTestCase(TestCase):
    @cached_property
    def ic(self):
        retval = Ice.initialize()
        self.addCleanup(retval.destroy)
        return retval

    @cached_property
    def adapter(self):
        adapter = self.ic.createObjectAdapterWithEndpoints('TestAdapter', 'default')
        adapter.activate()
        return adapter

    def wait_object_ready(self, proxy):
        attempts = 3
        proxy = proxy.ice_timeout(500)
        for _ in range(attempts):
            try:
                proxy.ice_ping()
                return
            except Ice.Exception:
                time.sleep(0.5)

        self.fail(f'Object not ready after {attempts} attempts')

    @cached_property
    def client_ic(self):
        client_ic = Ice.initialize()
        self.addCleanup(client_ic.destroy)
        return client_ic

    def create_proxy(self, proxy_str, cast):
        proxy = self.client_ic.stringToProxy(proxy_str)
        self.wait_object_ready(proxy)
        proxy = cast.checkedCast(proxy)
        self.assertIsNotNone(proxy)
        return proxy

    def create_server(self, main, props, *args):
        retval = ThreadIceServer(main, props, *args)
        self.addCleanup(retval.shutdown)
        return retval

    @cached_property
    def topic_manager(self):
        return IceStorm.TopicManagerPrx.checkedCast(
            self.client_ic.stringToProxy(self.topic_manager_strprx)
        )

    def get_topic(self, topic_name):
        try:
            return self.topic_manager.retrieve(topic_name)
        except IceStorm.NoSuchTopic:
            return self.topic_manager.create(topic_name)

    def get_topic_publisher(self, topic_name, cast):
        topic = self.get_topic(topic_name)
        publisher = topic.getPublisher()
        return cast.uncheckedCast(publisher)


def assert_listen_tcp(port, server_name=''):
    if server_name:
        server_name = f' for {server_name}'

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        result = s.connect_ex(('localhost', port))
        assert result == 0, f"TCP port {port} should be open{server_name}"


def assert_not_listen_tcp(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        result = s.connect_ex(('localhost', port))
        assert result != 0, f"TCP port {port} should be closed"


def pool_condition(condition_fn, ntries=3, interval_secs=1):
    retval = None

    for _ in range(ntries):
        time.sleep(interval_secs)
        if retval := condition_fn():
            return retval

    return retval
