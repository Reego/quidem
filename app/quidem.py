from enum import Enum

import math

# Represents a session instance

class UserVisibility(Enum):
    visible_to_all = 1
    visible_to_author = 2
    anonymous = 3

class VotingAlgorithm(Enum):

    @staticmethod
    def flinear(val):
        return val

    @staticmethod
    def fsquare(val):
        return math.pow(val, 2)

    @staticmethod
    def fcube(val):
        return math.pow(val, 3)

    @staticmethod
    def fexponential(val):
        return math.exp(val)

    @staticmethod
    def flogarithmic(val):
        return math.log(val)

    @classmethod
    def get_algorithm(cls, voting_algorithm):
        algorithms = [
            cls.flinear,
            cls.fsquare,
            cls.fcube,
            cls.fexponential,
            cls.flogarithmic
        ]

        return algorithms[voting_algorithm.value]

    linear = 0
    square = 1
    cube = 2
    exponential = 3
    logarithmic = 4

# Quidem configuration:
## user_visibility - dictates whether the other users in the party, or just the author, or neither may see the name of the users. If set to anonymous, users are not prompted for a username
## voting_algorithm - different voting algorithms that give different voting power to specific rank positions
## user_nominations_cap - limit to how many nominatinos a user can make
## allow_user_self_vote - whether or not the user may vote for his/her own nomination - not counted for author if user_nominations_cap is set to 0
## anti-vote_penalty - Penalty the user can enact on other nominations - min value of 0

# all settings are flexible and may be changed thru the author dashboard

# four phases:

## pre session creation - mutable user_visibility
## pre voting - mutable max_voting_slots -- nominate
## voting
## post voting - mutable everything else
## closed -- end

# Consumers will have access to the Quidem object, which will take an action and return a result
# This updated state will be returned to all users with varying degrees of data

class Phase(Enum):

    PRE_OPENING = 1
    PRE_VOTING = 2
    VOTING = 3
    POST_VOTING = 4
    CLOSED = 5

class Action(Enum):

    VOTE = 1
    JOIN = 2
    REMOVE_USER = 3
    NOMINATE = 4
    REMOVE_NOMINATION = 5
    NEXT_PHASE = 6
    CLOSE_SESSION = 7

class QuidemError(Exception):
    pass

class ActionError(QuidemError):
    pass

class ActionPhaseException(ActionError):
    """Raised when action is requested at an invalid phase"""
    pass

class ConsumerIdMismatchException(ActionError):
    """Raised when instance consumer id does not equal action consumer id"""
    def __init__(self, consumer_id, target_consumer_id):
        self.message = f'Consumer ID {consumer_id} belonging to consumer instance does not equal the targetted consumer ID {target_consumer_id} on the requested action.'
        super().__init__(self.message)

class Quidem():

    CHANGE_SETTING = 'CHANGE_SETTING'
    OPEN_SESSION = 'OPEN_SESSION'
    CLOSE_SESSION = 'CLOSE_SESSION'

    INITIAL_SESSION_ID = 1
    AUTHOR = 0

    def __init__(self, quidem_id = 0, settings={}):

        self.settings = {
            'user_visibility': settings.get('user_visibility') or UserVisibility.anonymous,
            'voting_algorithm': settings.get('voting_algorithm') or VotingAlgorithm.linear,
            'allow_user_nomination': settings.get('allow_user_nomination') or True,
            'allow_user_self_vote': settings.get('allow_user_self_vote') or False,
            'anti_vote_penalty': settings.get('anti_vote_penalty') or -1,
            'max_voting_slots': settings.get('max_voting_slots') or -1
        }

        self.quidem_id = quidem_id

        self._phase = Phase.PRE_OPENING

        self._author_nominations = []
        self._user_nominations = {} # list of all nomination objects - keys are the negative value of the user consumer_id

        self._votes = {}

        self._consumers = {} # dictionary of all consumer_id linked to their respective nicknames

        self._consumer_index = 0 # tracks consumer id so each consumer can have a unique id

    # unsure whether to keep this or not
    def get_state(self, is_author=False):
        if is_author:
            return self._get_state_author()
        else:
            return self._get_state_user()

    def _get_state_user(self):
        settings = dict(self.settings)
        del settings['anti_vote_penalty']
        del settings['voting_algorithm']
        state = {
            'settings': settings,
            'phase': self.phase
        }
        if self.phase is Phase.VOTING:
            state['nominations'] = self._get_nominations()
        return state

    def _get_state_author(self):
        state = {
            'nominations': self._get_nominations(),
            'users': self._consumers,
            'settings': self.settings,
            'phase': self.phase,
            'votes': self._votes
        }
        return state

    def _get_nominations(self):
        nominations = []
        i = 0
        for nomination in self._author_nominations:
            nominations.append({
                'nomination': nomination,
                'nomination_id': i
                })
            i += 1
        for consumer_id, nomination in self._user_nominations.items():
            nominations.append({
                'nomination': nomination,
                'nomination_id': consumer_id
            })
        return nominations

    def has_consumer(self, consumer_id):
        return consumer_id in self._consumers


    # action
    # - type - type of action
    # - consumer id - id belonging to the consumer
    # - body

    # returns whether or not there was a change in state
    def process_action(self, action, consumer_id, target_consumer_id, body):
        if consumer_id not in self._consumers and consumer_id != Quidem.AUTHOR:
            raise QuidemError('The given consumer ID is invalid')

        # Remove user
        if action == Action.REMOVE_USER:
            if consumer_id == target_consumer_id or (consumer_id == Quidem.AUTHOR and target_consumer_id != Quidem.AUTHOR):
                return self.remove_consumer(target_consumer_id)
            else:
                raise ConsumerIdMismatchException(target_consumer_id, consumer_id)

        # Vote
        elif action == Action.VOTE:
            nomination_id = body.get('nomination_id')
            vote_set = body.get('vote_set')
            return self.vote(consumer_id, nomination_id, vote_set)

        # Nominate
        elif consumer_id == target_consumer_id:
            if action == Action.NOMINATE:
                return self.nominate(target_consumer_id, body.get('nomination'))
            elif action == Action.REMOVE_NOMINATION:
                return self.remove_nomination(-consumer_id if consumer_id != Quidem.AUTHOR else body.get('nomination_id'))
            else:
                raise ActionError('Action ' + str(action) + ' does not exist')

        # No valid action found
        else:
            raise ConsumerIdMismatchException(target_consumer_id, consumer_id)

    # returns the consumer id for a new user
    # id for an author is always -1
    def new_consumer(self, nickname):
        if self.phase != Phase.PRE_VOTING:
            raise ActionPhaseException('Consumer creation can only be performed during PRE_VOTING phase')
        self._consumer_index += 1
        self._consumers[self._consumer_index] = nickname
        return self._consumer_index

    def force_remove_consumer(self, consumer_id):
        if consumer_id != Quidem.AUTHOR:
            if self.phase.value >= Phase.VOTING.value:
                self.remove_nomination(-consumer_id)
            del self._consumers[consumer_id]

    # removes nomination tied to consumer_id
    # then removes consumer
    def remove_consumer(self, consumer_id):
        if self.phase.value != Phase.PRE_VOTING.value:
            raise ActionPhaseException('Consumer removal can only be performed during PRE_VOTING phase')
        elif consumer_id != Quidem.AUTHOR:
            self.remove_nomination(-consumer_id)
            del self._consumers[consumer_id]
            return True
        return False

    # 'nomination_id' and 'vote_set' in body
    def vote(self, consumer_id, nomination_id, vote_set):
        if self.phase != Phase.VOTING:
            raise ActionPhaseException('Voting can only be performed during VOTING phase')
        elif nomination_id is None or vote_set is None:
            raise ActionError('Vote body arguments cannot be None')
        self._votes[consumer_id] = vote_set
        return True

    # 'nomination' in body
    def nominate(self, consumer_id, nomination):
        if self.phase.value > Phase.PRE_VOTING.value:
            raise ActionPhaseException('Nominating can only be performed during PRE_OPENING or PRE_VOTING phases')
        elif nomination is None or nomination.strip() == '':
            return False
        if consumer_id == Quidem.AUTHOR:
            self._author_nominations.append(nomination)
        else:
            self._user_nominations[-consumer_id] = nomination
        return True

    # 'nomination_id' in body
    def remove_nomination(self, nomination_id):
        if self.phase.value > Phase.PRE_VOTING.value:
            raise ActionPhaseException('Nomination Removal can only be performed during PRE_OPENING or PRE_VOTING phases')
        if nomination_id in self._user_nominations:
            del self._user_nominations[nomination_id]
        elif nomination_id >= 0 and nomination_id < len(self._author_nominations):
            del self._author_nominations[nomination_id]
        else:
            return False
        return True

    @property
    def phase(self):
        return self._phase

    def next_phase(self):

        # end quidem
        if self.phase is not Phase.CLOSED:
            self._phase = Phase(self._phase.value + 1)
        else:
            raise QuidemError('Phase already set to Phase.CLOSED')


    def force_close(self):
        self._phase = Phase.CLOSED
