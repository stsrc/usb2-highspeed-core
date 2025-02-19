#
# This file is part of LUNA.
#
# Copyright (c) 2020 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

""" Low-level USB transciever gateware -- control request components. """

import unittest
import functools
import operator

from amaranth            import Signal, Module, Elaboratable, Cat
from amaranth.hdl.rec    import Record, DIR_FANOUT

from .                   import USBSpeed
from .packet             import USBTokenDetector, USBDataPacketDeserializer, USBPacketizerTest
from .packet             import DataCRCInterface, USBInterpacketTimer, TokenDetectorInterface
from .packet             import InterpacketTimerInterface, HandshakeExchangeInterface
from ..stream            import USBInStreamInterface, USBOutStreamInterface
from ..request           import SetupPacket
from ...utils.bus        import OneHotMultiplexer

from ...test             import usb_domain_test_case



class RequestHandlerInterface:
    """ Record representing a connection between a control endpoint and a request handler.

    Components (I = input to request handler; O = output to control interface):
        *: setup                  -- Carries the most recent setup request to the handler.
        *: tokenizer              -- Carries information about any incoming token packets.

        # Control request status signals.
        I: data_requested         -- Pulsed to indicate that a data-phase IN token has been issued,
                                     and it's now time to respond (post-inter-packet delay).
        I: status_requested       -- Pulsed to indicate that a response to our status phase has been
                                     requested.

        # Address / configuration connections.
        O: address_changed        -- Strobe; pulses high when the device's address should be changed.
        O: new_address[7]         -- When `address_changed` is high, this field contains the address that
                                     should be adopted.

        I: active_config          -- The configuration number of the active configuration.
        O: config_changed         -- Strobe; pulses high when the device's configuration should be changed.
        O: new_config[8]          -- When `config_changed` is high, this field contains the configuration that
                                     should be applied.

        # Data rx signals.
        *: rx                     -- The receive stream for any data packets received.
        I: handshakes_in          -- Inputs that indicate when handshakes are detected from the host.
        I: rx_ready_for_response  -- Strobe that indicates that we're ready to respond to a complete transmission.
                                     Indicates that an interpacket delay has passed after an `rx_complete` strobe.
        I: rx_invalid:            -- Strobe that indicates an invalid data receipt. Indicates that the most recently
                                     received packet was corrupted; and should be discarded as invalid.

        # Data tx signals.
        *: tx                     -- The transmit stream for any packets generated by the handler.
        O: handshakes_out         -- Carries handshake generation requests.
    """

    def __init__(self):
        self.setup                 = SetupPacket()
        self.tokenizer             = TokenDetectorInterface()

        self.data_requested        = Signal()
        self.status_requested      = Signal()

        self.address_changed       = Signal()
        self.new_address           = Signal(7)

        self.active_config         = Signal(8)
        self.config_changed        = Signal()
        self.new_config            = Signal(8)

        self.rx                    = USBOutStreamInterface()
        self.rx_expected           = Signal()
        self.rx_ready_for_response = Signal()
        self.rx_invalid            = Signal()

        self.tx                    = USBInStreamInterface()
        self.handshakes_out        = HandshakeExchangeInterface(is_detector=True)
        self.handshakes_in         = HandshakeExchangeInterface(is_detector=False)
        self.tx_data_pid           = Signal(reset=1)



class USBRequestHandler(Elaboratable):
    """ Base class for USB request handler modules.

    I/O port:
        *: interface -- The RequestHandlerInterface we'll use.
    """

    def __init__(self):

        #
        # I/O port:
        #
        self.interface = RequestHandlerInterface()


    def send_zlp(self):
        """ Returns the statements necessary to send a zero-length packet."""

        tx = self.interface.tx

        # Send a ZLP along our transmit interface.
        # Our interface accepts 'valid' and 'last' without 'first' as a ZLP.
        return [
            tx.valid  .eq(1),
            tx.last   .eq(1)
        ]





class USBSetupDecoder(Elaboratable):
    """ Gateware responsible for detecting Setup transactions.

    I/O port:
        *: data_crc  -- Interface to the device's data-CRC generator.
        *: tokenizer -- Interface to the device's token detector.
        *: timer     -- Interface to the device's interpacket timer.

        I: speed     -- The device's current operating speed. Should be a USBSpeed
                        enumeration value -- 0 for high, 1 for full, 2 for low.
        *: packet    -- The SetupPacket record carrying our parsed output.
        I: ack       -- True when we're requesting that an ACK be generated.
    """
    SETUP_PID = 0b1101

    def __init__(self, *, utmi, standalone=False):
        """
        Paremeters:
            utmi           -- The UTMI bus we'll monitor for data. We'll consider this read-only.

            standalone     -- Debug parameter. If true, this module will operate without external components;
                              i.e. without an internal data-CRC generator, or tokenizer. In this case, tokenizer
                              and timer should be set to None; and will be ignored.
        """
        self.utmi          = utmi
        self.standalone    = standalone

        #
        # I/O port.
        #
        self.data_crc      = DataCRCInterface()
        self.tokenizer     = TokenDetectorInterface()
        self.timer         = InterpacketTimerInterface()
        self.speed         = Signal(2)


        self.packet        = SetupPacket()
        self.ack           = Signal()


    def elaborate(self, platform):
        m = Module()

        # If we're standalone, generate the things we need.
        if self.standalone:

            # Create our tokenizer...
            m.submodules.tokenizer = tokenizer = USBTokenDetector(utmi=self.utmi)
            m.d.comb += tokenizer.interface.connect(self.tokenizer)

            # ... and our timer.
            m.submodules.timer = timer = USBInterpacketTimer()
            timer.add_interface(self.timer)

            m.d.comb += timer.speed.eq(self.speed)


        # Create a data-packet-deserializer, which we'll use to capture the
        # contents of the setup data packets.
        m.submodules.data_handler = data_handler = \
            USBDataPacketDeserializer(utmi=self.utmi, max_packet_size=8, create_crc_generator=self.standalone)
        m.d.comb += self.data_crc.connect(data_handler.data_crc)

        # Instruct our interpacket timer to begin counting when we complete receiving
        # our setup packet. This will allow us to track interpacket delays.
        m.d.comb += self.timer.start.eq(data_handler.new_packet)

        # Keep our output signals de-asserted unless specified.
        m.d.usb += [
            self.packet.received  .eq(0),
        ]


        with m.FSM(domain="usb"):

            # IDLE -- we haven't yet detected a SETUP transaction directed at us
            with m.State('IDLE'):
                pid_matches     = (self.tokenizer.pid     == self.SETUP_PID)

                # If we're just received a new SETUP token addressed to us,
                # the next data packet is going to be for us.
                with m.If(pid_matches & self.tokenizer.new_token):
                    m.next = 'READ_DATA'


            # READ_DATA -- we've just seen a SETUP token, and are waiting for the
            # data payload of the transaction, which contains the setup packet.
            with m.State('READ_DATA'):

                # If we receive a token packet before we receive a DATA packet,
                # this is a PID mismatch. Bail out and start over.
                with m.If(self.tokenizer.new_token):
                    m.next = 'IDLE'

                # If we have a new packet, parse it as setup data.
                with m.If(data_handler.new_packet):

                    # If we got exactly eight bytes, this is a valid setup packet.
                    with m.If(data_handler.length == 8):

                        # Collect the signals that make up our bmRequestType [USB2, 9.3].
                        request_type = Cat(self.packet.recipient, self.packet.type, self.packet.is_in_request)

                        m.d.usb += [

                            # Parse the setup data itself...
                            request_type            .eq(data_handler.packet[0]),
                            self.packet.request     .eq(data_handler.packet[1]),
                            self.packet.value       .eq(Cat(data_handler.packet[2], data_handler.packet[3])),
                            self.packet.index       .eq(Cat(data_handler.packet[4], data_handler.packet[5])),
                            self.packet.length      .eq(Cat(data_handler.packet[6], data_handler.packet[7])),

                            # ... and indicate that we have new data.
                            self.packet.received  .eq(1),

                        ]

                        # We'll now need to wait a receive-transmit delay before initiating our ACK.
                        # Per the USB 2.0 and ULPI 1.1 specifications:
                        #   - A HS device needs to wait 8 HS bit periods before transmitting [USB2, 7.1.18.2].
                        #     Each ULPI cycle is 8 HS bit periods, so we'll only need to wait one cycle.
                        #   - We'll use our interpacket delay timer for everything else.
                        with m.If(self.timer.tx_allowed | (self.speed == USBSpeed.HIGH)):

                            # If we're a high speed device, we only need to wait for a single ULPI cycle.
                            # Processing delays mean we've already met our interpacket delay; and we can ACK
                            # immediately.
                            m.d.comb += self.ack.eq(1)
                            m.next = "IDLE"

                        # For other cases, handle the interpacket delay by waiting.
                        with m.Else():
                            m.next = "INTERPACKET_DELAY"


                    # Otherwise, this isn't; and we should ignore it. [USB2, 8.5.3]
                    with m.Else():
                        m.next = "IDLE"


            # INTERPACKET -- wait for an inter-packet delay before responding
            with m.State('INTERPACKET_DELAY'):

                # ... and once it equals zero, ACK and return to idle.
                with m.If(self.timer.tx_allowed):
                    m.d.comb += self.ack.eq(1)
                    m.next = "IDLE"

        return m


class USBSetupDecoderTest(USBPacketizerTest):
    FRAGMENT_UNDER_TEST = USBSetupDecoder
    FRAGMENT_ARGUMENTS = {'standalone': True}


    def initialize_signals(self):

        # Assume high speed.
        yield self.dut.speed.eq(USBSpeed.HIGH)


    def provide_reference_setup_transaction(self):
        """ Provide a reference SETUP transaction. """

        # Provide our setup packet.
        yield from self.provide_packet(
            0b00101101, # PID: SETUP token.
            0b00000000, 0b00010000 # Address 0, endpoint 0, CRC
        )

        # Provide our data packet.
        yield from self.provide_packet(
            0b11000011,   # PID: DATA0
            0b0_10_00010, # out vendor request to endpoint
            12,           # request number 12
            0xcd, 0xab,   # value  0xABCD (little endian)
            0x23, 0x01,   # index  0x0123
            0x78, 0x56,   # length 0x5678
            0x3b, 0xa2,   # CRC
        )


    @usb_domain_test_case
    def test_valid_sequence_receive(self):
        dut = self.dut

        # Before we receive anything, we shouldn't have a new packet.
        self.assertEqual((yield dut.packet.received), 0)

        # Simulate the host sending basic setup data.
        yield from self.provide_reference_setup_transaction()

        # We're high speed, so we should be ACK'ing immediately.
        self.assertEqual((yield dut.ack), 1)

        # We now should have received a new setup request.
        yield
        self.assertEqual((yield dut.packet.received), 1)

        # Validate that its values are as we expect.
        self.assertEqual((yield dut.packet.is_in_request), 0       )
        self.assertEqual((yield dut.packet.type),          0b10    )
        self.assertEqual((yield dut.packet.recipient),     0b00010 )
        self.assertEqual((yield dut.packet.request),       12      )
        self.assertEqual((yield dut.packet.value),         0xabcd  )
        self.assertEqual((yield dut.packet.index),         0x0123  )
        self.assertEqual((yield dut.packet.length),        0x5678  )


    @usb_domain_test_case
    def test_fs_interpacket_delay(self):
        dut = self.dut

        # Place our DUT into full speed mode.
        yield dut.speed.eq(USBSpeed.FULL)

        # Before we receive anything, we shouldn't have a new packet.
        self.assertEqual((yield dut.packet.received), 0)

        # Simulate the host sending basic setup data.
        yield from self.provide_reference_setup_transaction()

        # We shouldn't ACK immediately; we'll need to wait our interpacket delay.
        yield
        self.assertEqual((yield dut.ack), 0)

        # After our minimum interpacket delay, we should see an ACK.
        yield from self.advance_cycles(10)
        self.assertEqual((yield dut.ack), 1)



    @usb_domain_test_case
    def test_short_setup_packet(self):
        dut = self.dut

        # Before we receive anything, we shouldn't have a new packet.
        self.assertEqual((yield dut.packet.received), 0)

        # Provide our setup packet.
        yield from self.provide_packet(
            0b00101101, # PID: SETUP token.
            0b00000000, 0b00010000 # Address 0, endpoint 0, CRC
        )

        # Provide our data packet; but shorter than expected.
        yield from self.provide_packet(
            0b11000011,                                     # PID: DATA0
            0b00100011, 0b01000101, 0b01100111, 0b10001001, # DATA
            0b00011100, 0b00001110                          # CRC
        )

        # This shouldn't count as a valid setup packet.
        yield
        self.assertEqual((yield dut.packet.received), 0)


class USBRequestHandlerMultiplexer(Elaboratable):
    """ Multiplexes multiple RequestHandlers down to a single interface.

    Interfaces are added using .add_interface().

    I/O port:
        *: shared -- The post-multiplexer RequestHandler interface.
    """

    def __init__(self):

        #
        # I/O port
        #
        self.shared = RequestHandlerInterface()

        #
        # Internals
        #
        self._interfaces = []


    def add_interface(self, interface: RequestHandlerInterface):
        """ Adds a RequestHandlerInterface to the multiplexer.

        Arbitration is not performed; it's expected only one handler will be
        driving requests at a time.
        """
        self._interfaces.append(interface)


    def _multiplex_signals(self, m, *, when, multiplex, sub_bus=None):
        """ Helper that creates a simple priority-encoder multiplexer.

        Parmeters:
            when      -- The name of the interface signal that indicates that the `multiplex` signals
                         should be selected for output. If this signals should be multiplex, it
                         should be included in `multiplex`.
            multiplex -- The names of the interface signals to be multiplexed.
        """

        def get_signal(interface, name):
            """ Fetches an interface signal by name / sub_bus. """

            if sub_bus:
                bus = getattr(interface, sub_bus)
                return getattr(bus, name)
            else:
                return  getattr(interface, name)


        # We're building an if-elif tree; so we should start with an If entry.
        conditional = m.If

        for interface in self._interfaces:
            condition = get_signal(interface, when)

            with conditional(condition):

                # Connect up each of our signals.
                for signal_name in multiplex:

                    # Get the actual signals for our input and output...
                    driving_signal = get_signal(interface,   signal_name)
                    target_signal  = get_signal(self.shared, signal_name)

                    # ... and connect them.
                    m.d.comb += target_signal   .eq(driving_signal)

            # After the first element, all other entries should be created with Elif.
            conditional = m.Elif



    def elaborate(self, platform):
        m = Module()
        shared = self.shared


        #
        # Pass through signals being routed -to- our pre-mux interfaces.
        #
        for interface in self._interfaces:
            m.d.comb += [
                shared.setup                     .connect(interface.setup),
                shared.tokenizer                 .connect(interface.tokenizer),

                interface.data_requested         .eq(shared.data_requested),
                interface.status_requested       .eq(shared.status_requested),
                shared.handshakes_in             .connect(interface.handshakes_in),
                interface.active_config          .eq(shared.active_config),

                shared.rx                        .connect(interface.rx),
                interface.rx_ready_for_response  .eq(shared.rx_ready_for_response),
                interface.rx_invalid             .eq(shared.rx_invalid),
            ]

        #
        # Multiplex the signals being routed -from- our pre-mux interface.
        #
        self._multiplex_signals(m,
            when='address_changed',
            multiplex=['address_changed', 'new_address']
        )

        self._multiplex_signals(m,
            when='config_changed',
            multiplex=['config_changed', 'new_config']
        )

        # Connect up our transmit interface.
        m.submodules.tx_mux = tx_mux = OneHotMultiplexer(
            interface_type=USBInStreamInterface,
            mux_signals=('payload',),
            or_signals=('valid', 'first', 'last'),
            pass_signals=('ready',)
        )
        tx_mux.add_interfaces(i.tx for i in self._interfaces)
        m.d.comb += self.shared.tx.stream_eq(tx_mux.output)

        # Pass through the relevant PID from our data source.
        for i in self._interfaces:
            with m.If(i.tx.valid):
                m.d.comb += self.shared.tx_data_pid.eq(i.tx_data_pid)

        # OR together all of our handshake-generation requests.
        any_ack   = functools.reduce(operator.__or__, (i.handshakes_out.ack   for i in self._interfaces))
        any_nak   = functools.reduce(operator.__or__, (i.handshakes_out.nak   for i in self._interfaces))
        any_stall = functools.reduce(operator.__or__, (i.handshakes_out.stall for i in self._interfaces))

        m.d.comb += [
            shared.handshakes_out.ack    .eq(any_ack),
            shared.handshakes_out.nak    .eq(any_nak),
            shared.handshakes_out.stall  .eq(any_stall),
        ]

        return m


class StallOnlyRequestHandler(Elaboratable):
    """ Simple gateware request handler that only conditionally stalls requests.

    I/O port:
        *: interface -- The RequestHandlerInterface used to handle requests.
                        See its record definition for signal definitions.
    """

    def __init__(self, stall_condition):
        """
        Parameters:
            stall_condition -- A function that accepts a SetupRequest packet, and returns
                               an Amaranth conditional indicating whether we should stall.
        """

        self.condition = stall_condition

        #
        # I/O port
        #
        self.interface = RequestHandlerInterface()


    def elaborate(self, platform):
        m = Module()

        # If we have an opportunity to stall...
        with m.If(self.interface.data_requested | self.interface.status_requested):

            # ... and our stall condition is met ...
            with m.If(self.condition(self.interface.setup)):

                # ... do so.
                m.d.comb += self.interface.handshakes_out.stall.eq(1)

        return m



if __name__ == "__main__":
    unittest.main(warnings="ignore")
