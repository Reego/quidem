from enum import Enum
from os import path
import json

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

        query_data = self.scope['path'].split('/')[-2].split('&')
        self.quidem_id = int(query_data[0])
        self.client_key = int(query_data[1])
        self.nickname = query_data[2]

        if self.quidem_id > next_quidem_id: # requested a quidem with an id > the expected next id
            raise QuidemConsumerError('Invalid Quidem ID')
        else:
            self.group_name = self.get_group()

            # join quidem
            if self.quidem_id < next_quidem_id:
                self.consumer_id = None

                self.cache_key = str(self.quidem_id) + '&' + str(self.client_key)
                cache.set(self.cache_key, None)

                async_to_sync(self.channel_layer.group_add)(
                    self.group_name,
                    self.channel_name
                )
                self.accept()
                self._make_join_request()

                # # if failed to join, close connection
                # if not self.consumer_id:
                #     self.close()
                #     return

            # create quidem session
            else:
                self._create_quidem()
                cache.set('next_quidem_id', next_quidem_id + 1, None)

        if self.consumer_id == Quidem.AUTHOR:
            async_to_sync(self.channel_layer.group_add)(
                self.group_name,
                self.channel_name
            )
            self.accept()
            self._send_obj({
                'type': 'join',
                'key': self.client_key,
                'consumer_id': self.consumer_id
            })
            async_to_sync(self.channel_layer.group_send)(
                self.group_name,
                {
                    'type': 'broadcast_updated_state'
                }
            )

    def get_group(self):
        return f'quidem_{self.quidem_id}'

    def get_author_group(self):
        return f'author_quidem_{self.quidem_id}'

    def _send_obj(self, obj):
        self.send(text_data=json.dumps(obj))

    def receive_json(self, content):
        if self.consumer_id is None:
            self.consumer_id = cache.get(self.cache_key)
            cache.delete(self.cache_key)
            if not self.consumer_id:
                self.close()
                return

            self._send_obj({
                'type': 'join',
                'key': self.client_key,
                'consumer_id': self.consumer_id
            })
            print('JOINING', self.consumer_id)
            async_to_sync(self.channel_layer.group_send)(
                self.group_name,
                {
                    'type': 'broadcast_updated_state'
                }
            )
            return
        if self.consumer_id != Quidem.AUTHOR:
            async_to_sync(self.channel_layer.group_send)(
                self.get_author_group(),
                {
                    'type': 'process_action',
                    'content': content,
                    'sender': self.consumer_id
                }
            )
        else:
            self.process_action({'content':content, 'sender': self.consumer_id})

    # receives quidem event and calls next method
    def process_action(self, obj):

        content = obj['content']

        action = content.get('action')
        sender = int(obj['sender'])
        target_consumer_id = content.get('consumer_id')
        if target_consumer_id is not None:
            target_consumer_id = int(target_consumer_id)
        body = content.get('body')

         # closes quidem session
        if action == Action.CLOSE_SESSION.value:
            if sender == Quidem.AUTHOR:
                self.quidem.force_close()
                self._send_disconnect()
                self.close()

        # Ends session if phase is CLOSED
        elif action == Action.NEXT_PHASE.value:
            if sender == Quidem.AUTHOR:
                self.quidem.next_phase()
                self.broadcast_updated_state()

                # Ends session if phase is CLOSED
                if self.quidem.phase == Phase.CLOSED.value:
                    self._send_disconnect()
                    self.close()

                print(self.quidem.phase)

        # Changes Quidem settings
        elif action == Action.CHANGE_SETTING.value:
            if sender == Quidem.AUTHOR:
                updated_settings = {
                    'voting_algorithm': int(body.get('voting_algorithm', self.quidem.settings['voting_algorithm'])),
                    'max_voting_slots': self.quidem.settings['max_voting_slots'],
                    'question': self.quidem.settings['question']
                }
                if self.quidem.phase.value < Phase.VOTING.value:
                    updated_settings['max_voting_slots'] = int(body.get('max_voting_slots', self.quidem.settings['max_voting_slots']))
                    if self.quidem.phase.value == Phase.PRE_OPENING.value:
                        updated_settings['question'] = body.get('question', self.quidem.settings['question'])
                self.quidem.settings = updated_settings
                self.broadcast_updated_state()

        else:
            try:
                if self.quidem.process_action(action, sender, target_consumer_id, body):
                    if action == Action.REMOVE_USER.value:
                        self._send_disconnect(target_consumer_id)
                    self.broadcast_updated_state()
            # sends any potential ActionError's in processing the action back to the client
            except ActionError as err:
                print('\n\n-----ERROR--------')
                print(err)
                print('\n\n')

    def disconnect(self, close_code):
        if self.consumer_id:
            # group_discards the author group
            if self.consumer_id == Quidem.AUTHOR:
                async_to_sync(self.channel_layer.group_discard)(
                    self.get_author_group(),
                    self.channel_name
                )
            else:
                async_to_sync(self.channel_layer.group_send)(
                    self.get_author_group(),
                    {
                        'type': 'disconnect_consumer',
                        'consumer_id': self.consumer_id
                    }
                )

    def disconnect_consumer(self, obj):
        consumer_id = obj['consumer_id']
        if not self.quidem.has_consumer(consumer_id) and self.quidem.phase.value < Phase.CLOSED.value:
            self.quidem.force_remove_consumer(consumer_id)
            self.broadcast_updated_state()

    ### other methods

    # sends the updated state to all consumers, who then send it to the client end
    def broadcast_updated_state(self, obj=None):
        if self.consumer_id != Quidem.AUTHOR:
            return
        async_to_sync(self.channel_layer.group_send)(
            self.group_name,
            {
                'type': 'send_updated_state',
                'author': False,
                'state': self.quidem.get_state(),
                'votes': self.quidem._votes
            }
        )
        async_to_sync(self.channel_layer.group_send)(
            self.get_author_group(),
            {
                'type': 'send_updated_state',
                'author': True,
                'state': self.quidem.get_state(True)
            }
        )

    # only sends the state if the state is designated to that consumer's role
    def send_updated_state(self, obj):
        if (self.consumer_id == Quidem.AUTHOR) == obj['author']:
            state = dict(obj['state'])
            state['vote'] = state['votes'].get(self.consumer_id)
            state['user'] = self.consumer_id
            if self.consumer_id != Quidem.AUTHOR:
                del state['votes']
                state['nickname'] = self.nickname
                state['calculated_votes'] = state['calculated_votes'][0:1]
            self._send_obj({
                'type': 'state',
                'state': state
            })

    # method that sends message through channel to call response_to_join_request on the author consumer instance
    def _make_join_request(self):
        async_to_sync(self.channel_layer.group_send)(
            self.get_author_group(),
            {
                'type': 'response.to.join.request',
                'cache_key': self.cache_key,
                'nickname': self.nickname
            }
        )


    # method called on author consumer instance from visitor consumer requesting to join quidem session
    def response_to_join_request(self, obj):
        if self.consumer_id == Quidem.AUTHOR:
            if self.quidem.phase is Phase.PRE_VOTING:
                consumer_id = self.quidem.new_consumer(obj['nickname'])
                cache.set(obj['cache_key'], consumer_id)

    # broadcasts a disconnection event to all consumers in the group
    def _send_disconnect(self, consumer_filter=None):
        async_to_sync(self.channel_layer.group_send)(
            self.group_name,
            {
                'type': 'filtered.disconnect.consumer',
                'filter': consumer_filter
            }
        )

    # disconnects specific consumer
    def filtered_disconnect_consumer(self, obj):
        consumer_filter = obj.get('consumer_filter')

        # only removes if not the author and if the filter matches the consumer's id
        if self.consumer_id != Quidem.AUTHOR and (not consumer_filter or self.consumer_id == consumer_filter):
            self.close()

    # creates quidem instance
    def _create_quidem(self):
        author_group_name = self.get_author_group()

        self.quidem = Quidem(quidem_id=self.quidem_id)
        self.consumer_id = Quidem.AUTHOR

        async_to_sync(self.channel_layer.group_add)(
            author_group_name,
            self.channel_name
        )
