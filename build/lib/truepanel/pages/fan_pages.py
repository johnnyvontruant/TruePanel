from truepanel.menu.page import Page
from truepanel.hardware.fans import get_status


class FanRPMPage(Page):
    title = "Fans"

    def render(self, state=None):
        status = get_status()
        return [
            f'Fan1 {status["fan1_rpm"]:>5}RPM',
            f'Fan2 {status["fan2_rpm"]:>5}RPM',
        ]


class FanPWMPage(Page):
    title = "PWM"

    def render(self, state=None):
        status = get_status()
        return [
            f'PWM1 {status["pwm1"]:>3} {status["pwm1_mode"][:4]}',
            f'PWM2 {status["pwm2"]:>3} {status["pwm2_mode"][:4]}',
        ]
