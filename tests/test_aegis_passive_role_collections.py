from truepanel.aegis.passive_runtime import REQUIRED_ROLES, TrueNASRoleVerifier


class Delegate:
    def __init__(self, roles):
        self.roles = roles

    def call(self, method, *arguments):
        assert method == "auth.me"
        assert arguments == ()
        return {
            "local": True,
            "privilege": {"roles": self.roles},
        }


def test_role_verifier_accepts_set_from_truenas_api_client():
    roles = set(REQUIRED_ROLES) | {"DISK_READ", "POOL_READ"}

    result = TrueNASRoleVerifier(Delegate(roles)).verify()

    assert result["status"] == "VERIFIED"
    assert result["least_privilege_verified"] is True
    assert result["missing_roles"] == []
    assert result["forbidden_roles"] == []
    assert result["observed_role_count"] == len(roles)


def test_set_valued_roles_still_fail_closed_on_write_authority():
    roles = set(REQUIRED_ROLES) | {"DISK_WRITE"}

    result = TrueNASRoleVerifier(Delegate(roles)).verify()

    assert result["status"] == "HOLD"
    assert result["least_privilege_verified"] is False
    assert result["forbidden_roles"] == ["DISK_WRITE"]
