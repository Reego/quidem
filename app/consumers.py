from enum import Enum
from os import path

from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.core.cache import cache
from asgiref.sync import async_to_sync

from .quidem import Quidem, Action, Phase, ActionError

# first request sends quidem id
# if id == cached next_quidem_id, make a new quidem instance and increment next_quidem_id
# else request join

class QuidemConsumerError(Exception):
    pass

class QuidemConsumer(JsonWebsocketConsumer):

    DEFAULT_NICKNAME = 'Anonymous'

    ### Consumer methods

    # receives code from author
    def connect(self):

        next_quidem_id = cache.get('next_quidem_id')
        quidem_id = int(self.scope['path'].split('/')[-2])

        if quidem_id > next_quidem_id or quidem_id < Quidem.INITIAL_SESSION_ID: # requested a quidem with an id > the expected next id
            raise QuidemConsumerError('Invalid Quidem ID')
        else:
            self.group_name = QuidemConsumer.get_group(quidem_id)

            # join quidem
            if quidem_id < next_quidem_id:
                self.consumer_id = None
                self._make_join_request(QuidemConsumer.get_author_group(quidem_id))
                # if failed to join, close connection
                if not self.consumer_id:
                    self.close()
                    return

            # create quidem session
            else:
                self._create_quidem(quidem_id)
                cache.set('next_quidem_id', next_quidem_id + 1, None)

        self.accept()

        async_to_sync(self.channel_layer.group_add)
        (
            self.group_name,
            self.channel_name
        )

    @classmethod
    def get_group(cls, quidem_id):
        return f'quidem_{quidem_id}'

    @classmethod
    def get_author_group(cls, quidem_id):
        return f'author_quidem_{quidem_id}'

    # receives quidem event and calls next method
    def receive_json(self, content):
        print(content)
        action = content.get('action')
        target_consumer_id = content.get('consumer_id')
        body = content.get('body')


         # closes quidem session
        if action == Action.CLOSE_SESSION.value:
            if self.consumer_id == Quidem.AUTHOR:
                self.quidem.force_close()
                self._send_disconnect()
                self.close()

        # Ends session if phase is CLOSED
        elif action == Action.NEXT_PHASE.value:
            if self.consumer_id == Quidem.AUTHOR:
                self.quidem.next_phase()
                self._broadcast_updated_state()

                # Ends session if phase is CLOSED
                if self.quidem.phase == Phase.CLOSED.value:
                    self._send_disconnect()
                    self.close()
        else:
            try:
                # passes off action to quidem instance to be processed
                if self.quidem.process_action(action, self.consumer_id, target_consumer_id, body):
                    if action == Action.REMOVE_USER.value:
                        self._send_disconnect(target_consumer_id)
                    self._broadcast_updated_state()
            # sends any potential ActionError's in processing the action back to the client
            except ActionError as err:
                self.send({
                    'error': err
                })

    def disconnect(self, close_code):
        if self.consumer_id:
            # removes player when disconnected from websocket randomly
            if not self.quidem.has_consumer(self.consumer_id) and self.quidem.phase.value < Phase.CLOSED.value:
                    self.quidem.force_remove_consumer(self.consumer_id)
                    self._broadcast_updated_state()
            async_to_sync(self.channel_layer.group_discard)
            (
                self.group_name,
                self.channel_name
            )
            # group_discards the author group
            if self.consumer_id == Quidem.AUTHOR:
                async_to_sync(self.channel_layer.group_discard)
                (
                    f'author_{self.group_name}',
                    self.channel_name
                )

    ### other methods

    # sends the updated state to all consumers, who then send it to the client end
    def _broadcast_updated_state(self):
        async_to_sync(self.channel_layer.group_send)
        (
            self.group_name,
            {
                'type': 'send.updated.state',
                'author': False,
                'state': self.quidem.get_state()
            }
        )
        async_to_sync(self.channel_layer.group_send)
        (
            f'author_{self.group_name}',
            {
                'type': 'send.updated.state',
                'author': True,
                'state': self.quidem.get_state(True)
            }
        )

    # only sends the state if the state is designated to that consumer's role
    def _send_updated_state(self, obj):
        if (self.consumer_id == Quidem.AUTHOR) == obj['author']:
            self.send({
                'state': obj['state']
            })

    # method that sends message through channel to call response_to_join_request on the author consumer instance
    def _make_join_request(self, author_group_name):
        async_to_sync(self.channel_layer.group_send)
        (
            f'author_quim',
            {
                'type': 'response.to.join.request',
                'consumer': self
            }
        )

    # method called on author consumer instance from visitor consumer requesting to join quidem session
    def response_to_join_request(self, obj):
        if self.consumer_id == Quidem.AUTHOR:
            other = obj['consumer']
            if self.quidem.PHASE.value is PHASE.PRE_OPENING:
                nickname = other['session'].get('nickname', QuidemConsumer.DEFAULT_NICKNAME) if other['session'] else QuidemConsumer.DEFAULT_NICKNAME
                other.consumer_id = self.quidem.new_consumer(nickname)
                other.quidem = self.quidem

    # broadcasts a disconnection event to all consumers in the group
    def _send_disconnect(self, consumer_filter=None):
        async_to_sync(self.channel_layer.group_send)
        (
            self.group_name,
            {
                'type': 'disconnect.consumer',
                'filter': consumer_filter
            }
        )

    # disconnects specific consumer
    def _disconnect_consumer(self, obj):
        consumer_filter = obj.get('consumer_filter')

        # only removes if not the author and if the filter matches the consumer's id
        if self.consumer_id != Quidem.AUTHOR and (not consumer_filter or self.consumer_id == consumer_filter):
            self.close()

    # creates quidem instance
    def _create_quidem(self, quidem_id):
        author_group_name = QuidemConsumer.get_author_group(quidem_id)

        self.quidem = Quidem(quidem_id=quidem_id)
        self.consumer_id = Quidem.AUTHOR

        async_to_sync(self.channel_layer.group_add)
        (
            author_group_name,
            self.channel_name
        )
