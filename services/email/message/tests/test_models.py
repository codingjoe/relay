from services.email.message.models import Transmission


class TestTransmissionRepr:
    def test_repr__returns_pk(self):
        assert repr(Transmission(pk=1)) == "<Transmission 1>"
