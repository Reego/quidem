class TestException(Exception):

    def __init__(self, expression, message):
        self.message = 'BRUH'
        super().__init__('HOVITO')
