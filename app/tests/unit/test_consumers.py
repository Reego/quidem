import pytest
import asyncio

from asgiref.sync import async_to_sync
# from django.test import Client
from django.core.cache import cache
from channels.testing import WebsocketCommunicator

from ...quidem import Quidem, Phase, Action, ActionError

from ...consumers import QuidemConsumer, QuidemConsumerError
from ...routing import application

TEST_CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

class CallObject:

    def __init__(self):
        self.reset()

    def reset(self):
        self.called = False
        self.parameters = []

    def __str__(self):
        return f'called: {self.called}'

@pytest.mark.asyncio
class TestQuidemConsumer:

    @pytest.fixture
    def did_call(self, monkeypatch):
        def wrap(func_name, cls=QuidemConsumer, return_value=None):
            call_obj = CallObject()
            def inner(*args):
                nonlocal call_obj
                call_obj.called = True
                call_obj.parameters = args
                return return_value
            monkeypatch.setattr(cls, func_name, inner)
            return call_obj
        return wrap

    # @pytest.fixture
    # def consumer(self):
    #     client = Client()
    #     client.cookies['nickname'] = 'Bob'

    @pytest.fixture(autouse=True)
    def set_cache(self):
        cache.set('next_quidem_id', Quidem.INITIAL_SESSION_ID)

    @pytest.fixture
    async def get_setup(self, settings):
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS
        async def inner(quidem_session_id = Quidem.INITIAL_SESSION_ID, nickname = 'anonymous'):
            communicator = WebsocketCommunicator(
                application,
                f'ws/quidem/{quidem_session_id}&1002/',
                headers=[(
                    b'cookie',
                    f'nickname={nickname}'.encode('ascii')
                )]
            )

            connected, _ = await communicator.connect()
            return communicator
        return inner

    async def test_connect_invalid_quidem_id(self, get_setup):
        with pytest.raises(QuidemConsumerError):
            communicator = await get_setup(Quidem.INITIAL_SESSION_ID - 1)
            await communicator.disconnect()

    async def test_connection_valid_quidem_id_join(self, get_setup):
        communicator = await get_setup()
        await communicator.disconnect()

    async def test_join_quidem_session_author_disconnect(self, get_setup):
        author = await get_setup()

        joining_communicator = await get_setup(Quidem.INITIAL_SESSION_ID, 'Bob')

        await author.disconnect()

    async def test_join_quidem_session_guest_disconnect(self, get_setup):
        author = await get_setup()

        joining_communicator = await get_setup(Quidem.INITIAL_SESSION_ID, 'Bob')

        await joining_communicator.disconnect()
        await author.disconnect()

    # finished
    async def test_action_quidem_close_session(self, did_call, get_setup):
        call_obj_force_closed = did_call('force_close', cls=Quidem)
        call_obj_send_disconnect = did_call('_send_disconnect')

        author = await get_setup()

        await author.send_json_to({'action':Action.CLOSE_SESSION.value})
        await author.receive_nothing()

        assert call_obj_force_closed.called
        assert call_obj_send_disconnect.called

    # finished
    async def test_action_quidem_close_session_from_user(self, did_call, get_setup):
        call_obj_force_closed = did_call('force_close', cls=Quidem)
        call_obj_send_disconnect = did_call('_send_disconnect')

        author = await get_setup()
        user = await get_setup()

        await user.send_json_to({'action':Action.CLOSE_SESSION.value})
        await user.receive_nothing()

        assert not call_obj_force_closed.called
        assert not call_obj_send_disconnect.called

        await author.disconnect()

    # finished
    async def test_action_quidem_next_phase(self, did_call, get_setup):
        call_obj_next_phase = did_call('next_phase', cls=Quidem)
        call_obj_broadcast_updated_state = did_call('_broadcast_updated_state')
        call_obj_send_disconnect = did_call('_send_disconnect')

        author = await get_setup()

        await author.send_json_to({'action':Action.NEXT_PHASE.value})
        await author.receive_nothing()
        print('whaca?')
        assert call_obj_next_phase.called
        assert call_obj_broadcast_updated_state.called

        await author.disconnect()

    # finished
    async def test_action_quidem_next_phase_from_user(self, did_call, get_setup):
        call_obj_next_phase = did_call('next_phase', cls=Quidem)
        call_obj_broadcast_updated_state = did_call('_broadcast_updated_state')
        call_obj_send_disconnect = did_call('_send_disconnect')

        author = await get_setup()
        user = await get_setup()

        await user.send_json_to({'action':Action.NEXT_PHASE.value})
        await author.receive_nothing()

        assert not call_obj_next_phase.called
        assert call_obj_broadcast_updated_state.called
        assert not call_obj_send_disconnect.called

        await author.disconnect()

    # finished
    async def test_other_valid_actions(self, monkeypatch, did_call, get_setup):
        call_obj_process_action = did_call('process_action', cls=Quidem, return_value=True)
        call_obj_broadcast_updated_state = did_call('_broadcast_updated_state', cls=QuidemConsumer)

        author = await get_setup()

        await author.send_json_to({'action': Action.VOTE.value})
        await author.receive_nothing()

        assert call_obj_process_action.called
        assert call_obj_broadcast_updated_state.called

        await author.disconnect()

    # finished
    async def test_remove_user_action(self, did_call, get_setup):
        call_obj_process_action = did_call('process_action', cls=Quidem, return_value=True)
        call_obj_send_disconnect = did_call('_send_disconnect')
        call_obj_broadcast_updated_state = did_call('_broadcast_updated_state')

        author = await get_setup()

        await author.send_json_to({'action': Action.REMOVE_USER.value})
        await author.receive_nothing()

        assert call_obj_process_action.called
        assert call_obj_send_disconnect.called
        assert call_obj_broadcast_updated_state.called

        await author.disconnect()

    # finished
    async def no_test_other_invalid_action_error_message(self, monkeypatch, get_setup):
        def raise_error(*args):
            raise ActionError()
        monkeypatch.setattr(Quidem, 'process_action', raise_error)
        author = await get_setup()

        await author.send_json_to({'action':'0'})
        res = await author.receive_json_from()
        print(res)
        assert 'error' in res

        await author.disconnect()
