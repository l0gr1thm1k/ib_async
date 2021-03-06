import pytest

from ib_async.errors import OutdatedServerError
from ib_async.functionality.market_data import MarketDataMixin
from ib_async.messages import Incoming, Outgoing
from ib_async.protocol_versions import ProtocolVersion
from ib_async.tick_types import MarketDataTimeliness, TickType

from .utils import FunctionalityTestHelper


class MixinFixture(MarketDataMixin, FunctionalityTestHelper):
    pass


def test_change_market_data_timeliness():
    client = MixinFixture()

    client.change_market_data_timeliness(MarketDataTimeliness.DelayedFrozen)
    client.assert_message_sent(Outgoing.REQ_MARKET_DATA_TYPE, 1, 4)


def test_subscribe():
    client = MixinFixture()
    instrument = client.test_instrument

    received = []

    def handler(tick):
        received.append(tick)

    instrument.market_data_tick_types = [100, 101]

    # Adding a handler should trigger msg
    instrument.on_market_data += handler
    client.assert_one_message_sent(Outgoing.REQ_MKT_DATA, '11', '43', instrument, False, '100,101', False, None)

    # Changing params should trigger resubscription
    instrument.market_data_tick_types = [100]
    client.assert_one_message_sent(Outgoing.REQ_MKT_DATA, '11', '43', instrument, False, '100', False, None)

    # Check that timeliness is correctly delivered to the instrument
    client.fake_incoming(Incoming.MARKET_DATA_TYPE, 1, 43, 3)
    assert instrument.market_data_timeliness == MarketDataTimeliness.Delayed

    # Test the various messages that deliver market data
    client.fake_incoming(Incoming.TICK_PRICE, 1, 43,
                         TickType.DelayedAsk, 13.37, 13, 0)

    assert instrument._tick_data[TickType.DelayedAsk] == 13.37
    assert instrument._tick_data[TickType.DelayedAskSize] == 13.0

    client.fake_incoming(Incoming.TICK_GENERIC, 1, 43,
                         TickType.MarkPrice, 1.21)

    assert instrument._tick_data[TickType.MarkPrice] == 1.21

    client.fake_incoming(Incoming.TICK_STRING, 1, 43,
                         TickType.Shortable, 1)

    assert instrument._tick_data[TickType.Shortable] == "1"

    client.fake_incoming(Incoming.TICK_SIZE, 1, 43,
                         TickType.BidSize, 1337)

    assert instrument._tick_data[TickType.BidSize] == 1337

    # Check the event handler was triggered in the right order
    assert received == [TickType.DelayedAsk, TickType.DelayedAskSize,
                        TickType.MarkPrice, TickType.Shortable, TickType.BidSize]

    # IB also sends TICK_REQ_PARAMS. Check that, too
    client.fake_incoming(Incoming.TICK_REQ_PARAMS, 43, 0.001, 'LSE', 4)

    assert instrument.minimum_tick == 0.001
    assert instrument.bbo_exchange == 'LSE'
    assert instrument.snapshot_permissions == 4

    # Removing the last handler should trigger an unsubscription
    instrument.on_market_data -= handler
    client.assert_one_message_sent(Outgoing.CANCEL_MKT_DATA, 2, 43)


def test_fetch():
    client = MixinFixture()
    instrument = client.test_instrument

    future = instrument.fetch_market_data()
    assert not future.done()

    client.assert_one_message_sent(Outgoing.REQ_MKT_DATA, 11, 43, 172604153, 'LLOY', 'STK', partial_match=True)

    client.fake_incoming(Incoming.TICK_SNAPSHOT_END, 1, 43)
    assert future.done()


def test_regulatory_snapshot():
    client = MixinFixture()
    client.version = ProtocolVersion.MIN_CLIENT
    instrument = client.test_instrument
    with pytest.raises(OutdatedServerError):
        client.get_market_data(instrument, regulatory_snapshot=True)
