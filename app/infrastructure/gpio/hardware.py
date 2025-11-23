# app/infrastructure/gpio/hardware.py

try:
    import RPi.GPIO as RPiGPIO

    REAL_GPIO = True
except (ImportError, RuntimeError):
    REAL_GPIO = False


class MockGPIO:
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"
    LOW = 0
    HIGH = 1

    mock_state = {}

    @staticmethod
    def setwarnings(flag):
        print(f"[MOCK GPIO] setwarnings({flag})")

    @staticmethod
    def setmode(mode):
        print(f"[MOCK GPIO] setmode({mode})")

    @staticmethod
    def setup(pin, mode):
        print(f"[MOCK GPIO] setup(pin={pin}, mode={mode})")
        if pin not in MockGPIO.mock_state:
            MockGPIO.mock_state[pin] = MockGPIO.HIGH

    @staticmethod
    def output(pin, state):
        print(f"[MOCK GPIO] output(pin={pin}, state={state})")
        MockGPIO.mock_state[pin] = state

    @staticmethod
    def input(pin):
        state = MockGPIO.mock_state.get(pin, MockGPIO.HIGH)
        print(f"[MOCK GPIO] input(pin={pin}) -> {state}")
        return state


GPIO = RPiGPIO if REAL_GPIO else MockGPIO
