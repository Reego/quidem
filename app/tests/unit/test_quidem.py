import pytest

from ...quidem import Quidem, Phase, Action, QuidemError, ActionPhaseException, ActionError, ConsumerIdMismatchException

class CallObject:

    def __init__(self):
        self.reset()

    def reset(self):
        self.called = False
        self.parameters = []

class TestQuidem:

    @pytest.fixture
    def quidem(self):
        return Quidem()

    @pytest.fixture
    def did_call(self, monkeypatch):
        def wrap(func_name):
            call_obj = CallObject()
            def inner(*args):
                nonlocal call_obj
                call_obj.called = True
                call_obj.parameters = args
                return None
            monkeypatch.setattr(Quidem, func_name, inner)
            return call_obj
        return wrap

    # finished
    def test_get_state_user(self, did_call):
        call_obj = did_call('_get_nominations')

        quidem = Quidem()
        quidem._phase = Phase.VOTING

        quidem.settings = {
            'user_visibility': False,
            'voting_algorithm': False,
            'allow_user_nomination': False,
            'extra_field': True
        }

        state_user = quidem.get_state()

        assert 'voting_algorithm' in quidem.settings
        assert 'voting_algorithm' not in state_user['settings']
        assert 'extra_field' in state_user['settings']

        assert 'nominations' in state_user
        assert state_user['phase'] == quidem.phase

        assert call_obj.called

        quidem._phase = None

        state_user = quidem.get_state()

        assert 'nominations' not in state_user

    # finished
    def test_get_state_author(self, monkeypatch):
        monkeypatch.setattr(Quidem, '_get_nominations', lambda x: None)

        quidem = Quidem()

        quidem.settings = {
            'user_visibility': False,
            'voting_algorithm': False,
            'allow_user_nomination': False,
            'extra_field': True
        }

        state_author = quidem.get_state(True)

        assert state_author['settings'] == quidem.settings
        assert 'nominations' in state_author
        assert state_author['users'] == quidem._consumers
        assert state_author['phase'] == quidem.phase.value

    # finished
    def test_get_nominations(self, quidem):

        author_nom_1 = 'nom_1'
        author_nom_2 = 'nom_2'
        author_nom_3 = 'nom_3'

        user_1 = 2
        user_nom_1 = 'nom_4'
        user_2 = 4
        user_nom_2 = 'nom_5'
        user_3 = 5
        user_nom_3 = 'nom_6'

        quidem._author_nominations = [
            author_nom_1,
            author_nom_2,
            author_nom_3
        ]

        quidem._user_nominations = {
            -user_1: user_nom_1,
            -user_2: user_nom_2,
            -user_3: user_nom_3
        }

        nominations = quidem._get_nominations()

        to_check = [*range(len(quidem._author_nominations)), -user_2, -user_1, -user_3]

        initial_length_author_nominations = len(quidem._author_nominations)
        initial_length_user_nominations = len(quidem._user_nominations.values())
        checked_author_nominations = 0
        checked_user_nominations = 0

        i = 0
        for nomination in nominations:
            nomination_id = nomination['nomination_id']
            if nomination_id in to_check:
                if nomination_id < 0:
                    del quidem._user_nominations[nomination_id]
                    checked_user_nominations += 1
                else:
                    del quidem._author_nominations[quidem._author_nominations.index(nomination['nomination'])]
                    checked_author_nominations += 1
                del to_check[to_check.index(nomination_id)]
            else:
                print(nomination)
            i += 1
        assert len(quidem._author_nominations) == 0
        assert len(quidem._user_nominations.values()) == 0
        assert checked_author_nominations == initial_length_author_nominations
        assert checked_user_nominations == initial_length_user_nominations
        assert len(to_check) == 0

    # finished
    def test_process_action_exceptions(self, did_call):
        call_obj_remove_consumer = did_call('remove_consumer')
        call_obj_vote = did_call('remove_consumer')
        call_obj_nominate = did_call('nominate')
        call_obj_remove_nomination = did_call('remove_nomination')

        quidem = Quidem()

        actions = [
            {
                'params': [Action.REMOVE_USER, 1, 0, None],
                'call_obj': call_obj_remove_consumer,
                'err': ConsumerIdMismatchException,
            },
            {
                'params': [Action.NOMINATE, 4, 2, None],
                'call_obj': call_obj_remove_consumer,
                'err': ActionError,
            },
            {
                'params': [Action.REMOVE_NOMINATION, 3, 2, None],
                'call_obj': call_obj_remove_consumer,
                'err': ActionError,
            }
        ]

        for action in actions:
            quidem._consumers = {action['params'][1]: None}
            with pytest.raises(action['err']):
                quidem.process_action(*action['params'])
            assert not action['call_obj'].called

    # finished
    def test_remove_consumer_exceptions(self, quidem):
        quidem._consumers = {1: None}
        actions = [
            {
                'consumer_id': 1,
                'target_consumer_id': 1,
                'phase': Phase.PRE_OPENING,
            },
            {
                'consumer_id': 1,
                'target_consumer_id': 1,
                'phase': Phase.VOTING,
            },
            {
                'consumer_id': 1,
                'target_consumer_id': 1,
                'phase': Phase.POST_VOTING,
            },
            {
                'consumer_id': 1,
                'target_consumer_id': 1,
                'phase': Phase.CLOSED,
            }
        ]

        for action in actions:
            with pytest.raises(ActionPhaseException):
                quidem.process_action(Action.REMOVE_USER, action['consumer_id'], action['target_consumer_id'], None)

    # finished
    def test_remove_consumer(self, did_call):

        call_obj = did_call('remove_nomination')

        initial_consumers = {
            2: 'Anonymous',
            3: 'Bob',
            5: 'Name'
        }
        actions = [
            {
                'consumer_id': 2,
                'target_consumer_id': 2,
                'return': True
            },
            {
                'consumer_id': 0,
                'target_consumer_id': 5,
                'return': True
            },
            {
                'consumer_id': 3,
                'target_consumer_id': 3,
                'return': True
            },
            {
                'consumer_id': Quidem.AUTHOR,
                'target_consumer_id': Quidem.AUTHOR,
                'return': False
            },
        ]

        quidem = Quidem()
        quidem._phase = Phase.PRE_VOTING

        i = 0
        for action in actions:
            i += 1
            call_obj.reset()
            quidem._consumers = dict(initial_consumers)
            assert action['return'] == quidem.process_action(Action.REMOVE_USER, action['consumer_id'], action['target_consumer_id'], None)
            assert action['return'] == call_obj.called
            assert action['return'] == ((not action['target_consumer_id'] == Quidem.AUTHOR) and action['target_consumer_id'] not in quidem._consumers)

    # finished
    def test_new_consumer_exception(self, quidem):
        phases = [Phase.PRE_OPENING, Phase.VOTING, Phase.POST_VOTING, Phase.CLOSED]

        initial_quidem_consumer_index = quidem._consumer_index

        for phase in phases:
            quidem._phase = phase
            with pytest.raises(ActionPhaseException):
                quidem.new_consumer('nickname')

    # finished
    def test_new_consumer(self, quidem):
        quidem._phase = Phase.PRE_VOTING

        nickname = 'anonymous'
        prev_consumer_id = quidem._consumer_index

        for i in range(10):
            nickname = nickname + str(i)
            consumer_id = quidem.new_consumer(nickname)
            assert consumer_id == prev_consumer_id + 1
            prev_consumer_id = consumer_id
            assert quidem._consumers[consumer_id] == nickname

    def test_vote_exceptions(self, quidem):

        quidem._consumers = {1: None}

        phases = [Phase.PRE_OPENING, Phase.PRE_VOTING, Phase.POST_VOTING, Phase.CLOSED]

        for phase in phases:
            quidem._phase = phase
            with pytest.raises(ActionPhaseException):
                quidem.process_action(Action.VOTE, 1, 1, {})

        phases.append(Phase.VOTING)

        for phase in phases:
            quidem._phase = phase
            with pytest.raises(ActionError):
                quidem.process_action(Action.VOTE, 1, 1, {})

    # finished
    def test_vote(self, quidem):
        quidem._phase = Phase.VOTING
        quidem._consumers = {1: None}

        actions = [
            {
                'consumer_id': 1,
                'target_consumer_id': 1,
                'body': {
                    'nomination_id': 2,
                    'vote_set': 'vote'
                }
            },
            {
                'consumer_id': 0,
                'target_consumer_id': 1,
                'body': {
                    'nomination_id': 2,
                    'vote_set': 'vote'
                }
            },
            {
                'consumer_id': 0,
                'target_consumer_id': 0,
                'body': {
                    'nomination_id': 2,
                    'vote_set': 'vote'
                }
            },
        ]

        for action in actions:
            quidem._votes = {}
            quidem.process_action(
                Action.VOTE,
                action['consumer_id'],
                action['target_consumer_id'],
                action['body']
            )
            assert action['consumer_id'] in quidem._votes
            assert quidem._votes[action['consumer_id']] is action['body']['vote_set']

    # finished
    def test_nominate_exceptions(self, quidem):
        quidem._consumers = {1: None}

        phases = [Phase.VOTING, Phase.POST_VOTING, Phase.CLOSED]
        for phase in phases:
            quidem._phase = phase
            with pytest.raises(ActionPhaseException):
                quidem.process_action(Action.NOMINATE, 0, 0, {})
            with pytest.raises(ActionPhaseException):
                quidem.process_action(Action.NOMINATE, 1, 1, {})

    # finished
    def test_nominate(self, quidem):

        quidem._consumers = {2: None, 5: None}
        quidem._phase = Phase.PRE_VOTING

        actions = [
            {
                'consumer_id': Quidem.AUTHOR,
                'target_consumer_id': Quidem.AUTHOR,
                'nomination': 'nomination1',
                'expected_length': 3,
                'return': True
            },
            {
                'consumer_id': Quidem.AUTHOR,
                'target_consumer_id': Quidem.AUTHOR,
                'nomination': ' ',
                'expected_length': 2,
                'return': False
            },
            {
                'consumer_id': 2,
                'target_consumer_id': 2,
                'nomination': 'nomination2',
                'expected_length': 2,
                'return': True
            },
            {
                'consumer_id': 2,
                'target_consumer_id': 2,
                'nomination': '',
                'expected_length': 2,
                'return': False
            },
            {
                'consumer_id': 5,
                'target_consumer_id': 5,
                'nomination': 'nomination3',
                'expected_length': 3,
                'return': True
            }
        ]

        initial_state = {
            'author_nominations': ['wow', 'okay'],
            'user_nominations': {
                -2: 'Huh?',
                -3: 'Another one'
            }
        }

        for action in actions:
            quidem._author_nominations = list(initial_state['author_nominations'])
            quidem._user_nominations = dict(initial_state['user_nominations'])
            nomination = action['nomination']
            assert action['return'] == quidem.process_action(Action.NOMINATE, action['consumer_id'], action['target_consumer_id'], {'nomination': action['nomination']})
            if action['consumer_id'] == Quidem.AUTHOR:
                assert action['expected_length'] == len(quidem._author_nominations)
                assert action['return'] == (action['nomination'] in quidem._author_nominations)
            else:
                assert action['expected_length'] == len(quidem._user_nominations.values())
                if -action['consumer_id'] not in initial_state['user_nominations']:
                    assert action['return'] == ((-action['consumer_id']) in quidem._user_nominations)

    def test_remove_nomination_exceptions(self, quidem):
        quidem._consumers = {1: None}

        phases = [Phase.VOTING, Phase.POST_VOTING, Phase.CLOSED]

        for phase in phases:
            quidem._phase = phase
            with pytest.raises(ActionPhaseException):
                quidem.process_action(Action.REMOVE_NOMINATION, 1, 1, None)

    # finished
    def test_remove_nomination_author(self, quidem):

        initial_quidem_state = {
            'consumers': {
                1: '',
                2: '',
                3: ''
            },
            'author_nominations': ['anom1', 'anom2', 'anom3'],
            'user_nominations': {
                -2: 'nom1',
                -3: 'nom2'
            }
        }

        actions = [
            {
                'phase': Phase.PRE_OPENING,
                'nomination_id': 1,
                'return': True
            },
            {
                'phase': Phase.PRE_OPENING,
                'nomination_id': 0,
                'return': True
            },
            {
                'phase': Phase.PRE_VOTING,
                'nomination_id': 2,
                'return': True
            },
            {
                'phase': Phase.PRE_OPENING,
                'nomination_id': -1,
                'return': False
            },
            {
                'phase': Phase.PRE_VOTING,
                'nomination_id': 3,
                'return': False
            },
        ]

        for action in actions:
            quidem._author_nominations = list(initial_quidem_state['author_nominations'])
            quidem._user_nominations = dict(initial_quidem_state['user_nominations'])
            quidem._consumers = dict(initial_quidem_state['consumers'])

            nomination_id = action['nomination_id']
            original_nom = quidem._author_nominations[nomination_id] if nomination_id in quidem._author_nominations else None
            assert action['return'] == quidem.process_action(Action.REMOVE_NOMINATION, Quidem.AUTHOR, Quidem.AUTHOR, {'nomination_id': action['nomination_id']})
            if original_nom:
                assert original_nom not in quidem._author_nominations
    # finished
    def test_remove_nomination_user(self, quidem):

        initial_quidem_state = {
            'consumers': {
                1: '',
                2: '',
                3: ''
            },
            'author_nominations': ['anom1', 'anom2', 'anom3'],
            'user_nominations': {
                -2: 'nom1',
                -3: 'nom2'
            }
        }

        actions = [
            {
                'phase': Phase.PRE_OPENING,
                'consumer_id': 2,
                # 'nomination_id': -1,
                'return': True
            },
            {
                'phase': Phase.PRE_OPENING,
                'consumer_id': 2,
                # 'nomination_id': 2,
                'return': True
            },
            {
                'phase': Phase.PRE_VOTING,
                'consumer_id': 1,
                # 'nomination_id': 0,
                'return': False
            },
            {
                'phase': Phase.PRE_OPENING,
                'consumer_id': 3,
                # 'nomination_id': 3,
                'return': True
            }
        ]

        for action in actions:
            quidem._author_nominations = list(initial_quidem_state['author_nominations'])
            quidem._user_nominations = dict(initial_quidem_state['user_nominations'])
            quidem._consumers = dict(initial_quidem_state['consumers'])

            nomination_id = -action['consumer_id']
            original_nom = quidem._user_nominations[nomination_id] if nomination_id in quidem._user_nominations else None
            assert action['return'] == quidem.process_action(Action.REMOVE_NOMINATION, action['consumer_id'], action['consumer_id'], None)
            if original_nom:
                assert -action['consumer_id'] not in quidem._user_nominations

    # finished
    def test_next_phase(self, quidem):
        assert quidem.phase == Phase.PRE_OPENING
        quidem.next_phase()
        assert quidem.phase is Phase.PRE_VOTING
        quidem.next_phase()
        assert quidem.phase is Phase.VOTING
        quidem.next_phase()
        assert quidem.phase is Phase.POST_VOTING
        quidem.next_phase()
        assert quidem.phase is Phase.CLOSED
        with pytest.raises(QuidemError):
            quidem.next_phase()
