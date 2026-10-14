"""Copy to modules/<name>.py (no leading underscore) to register a scenario.

The leading underscore keeps this file out of auto-discovery.

class CheckoutOom(ScenarioModule):
    name = "checkout-oom"
    flag_key = "S-V-checkoutOomRollout"  # S-I…S-IV = field demos, S-TEST- = controller test
    flag_type = "boolean"
    default = False

    def reconcile(self, cluster, value) -> None:
        if not value:
            cluster.delete_deployment("checkout-api-oom")
            cluster.delete_configmap("checkout-api-oom-script")
            return
        cluster.apply_configmap({...}, self.name)
        cluster.apply_deployment({...}, self.name)
"""
