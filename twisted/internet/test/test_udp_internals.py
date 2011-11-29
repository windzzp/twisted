# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the internal implementation details of L{twisted.internet.udp}.
"""

import socket

from twisted.trial import unittest
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import udp
from twisted.python.runtime import platformType

if platformType == 'win32':
    from errno import WSAEWOULDBLOCK as EWOULDBLOCK
    from errno import WSAECONNREFUSED as ECONNREFUSED
else:
    from errno import EWOULDBLOCK
    from errno import ECONNREFUSED



class StringUDPSocket(object):
    """
    A fake UDP socket object, which returns a fixed sequence of strings and/or
    socket errors.  Useful for testing.

    @ivar retvals: A C{list} containing either strings or C{socket.error}s.

    @ivar connectedAddr: The address the socket is connected to.
    """

    def __init__(self, retvals):
        self.retvals = retvals
        self.connectedAddr = None


    def connect(self, addr):
        self.connectedAddr = addr


    def recvfrom(self, size):
        """
        Return (or raise) the next value from C{self.retvals}.
        """
        ret = self.retvals.pop(0)
        if isinstance(ret, socket.error):
            raise ret
        return ret, None



class KeepReads(DatagramProtocol):
    """
    Accumulate reads in a list.
    """

    def __init__(self):
        self.reads = []


    def datagramReceived(self, data, addr):
        self.reads.append(data)



class ErrorsTestCase(unittest.TestCase):
    """
    Error handling tests for C{udp.Port}.
    """

    def test_socketReadNormal(self):
        """
        Socket reads with some good data followed by a socket error which can
        be ignored causes reading to stop, and no log messages to be logged.
        """
        # Add a fake error to the list of ignorables:
        udp._sockErrReadIgnore.append(-7000)
        self.addCleanup(udp._sockErrReadIgnore.remove, -7000)

        protocol = KeepReads()
        port = udp.Port(None, protocol)
        port._state = udp.LISTENING

        # Normal result, no errors
        port.socket = StringUDPSocket(
            ["result", "123", socket.error(-7000), "456",
             socket.error(-7000)])
        port.doRead()
        # Read stops on error:
        self.assertEqual(protocol.reads, ["result", "123"])
        port.doRead()
        self.assertEqual(protocol.reads, ["result", "123", "456"])


    def test_readImmediateError(self):
        """
        If the socket is unconnected, socket reads with an immediate
        connection refusal are ignored, and reading stops. The protocol's
        C{connectionRefused} method is not called.
        """
        # Add a fake error to the list of those that count as connection
        # refused:
        udp._sockErrReadRefuse.append(-6000)
        self.addCleanup(udp._sockErrReadRefuse.remove, -6000)

        protocol = KeepReads()
        # Fail if connectionRefused is called:
        protocol.connectionRefused = lambda: 1/0

        port = udp.Port(None, protocol)
        port._state = udp.LISTENING

        # Try an immediate "connection refused"
        port.socket = StringUDPSocket(["a", socket.error(-6000), "b",
                                       socket.error(EWOULDBLOCK)])
        port.doRead()
        # Read stops on error:
        self.assertEqual(protocol.reads, ["a"])
        # Read again:
        port.doRead()
        self.assertEqual(protocol.reads, ["a", "b"])


    def test_connectedReadImmediateError(self):
        """
        If the socket connected, socket reads with an immediate
        connection refusal are ignored, and reading stops. The protocol's
        C{connectionRefused} method is called.
        """
        # Add a fake error to the list of those that count as connection
        # refused:
        udp._sockErrReadRefuse.append(-6000)
        self.addCleanup(udp._sockErrReadRefuse.remove, -6000)

        protocol = KeepReads()
        refused = []
        protocol.connectionRefused = lambda: refused.append(True)

        port = udp.Port(None, protocol)
        port.socket = StringUDPSocket(["a", socket.error(-6000), "b",
                                       socket.error(EWOULDBLOCK)])
        port._state = udp.LISTENING
        port.connect("127.0.0.1", 9999)
        port._state = udp.LISTENING_CONNECTED

        # Read stops on error:
        port.doRead()
        self.assertEqual(protocol.reads, ["a"])
        self.assertEqual(refused, [True])

        # Read again:
        port.doRead()
        self.assertEqual(protocol.reads, ["a", "b"])
        self.assertEqual(refused, [True])


    def test_readUnknownError(self):
        """
        Socket reads with an unknown socket error are raised.
        """
        protocol = KeepReads()
        port = udp.Port(None, protocol)
        port._state = udp.LISTENING

        # Some good data, followed by an unknown error
        port.socket = StringUDPSocket(["good", socket.error(-1337)])
        self.assertRaises(socket.error, port.doRead)
        self.assertEqual(protocol.reads, ["good"])
