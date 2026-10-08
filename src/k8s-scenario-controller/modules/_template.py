"""Copy to modules/<name>.py (no leading underscore) to register a scenario.

The leading underscore keeps this file out of auto-discovery.

class CheckoutOom(ScenarioModule):
    name = "checkout-oom"
    flag_key = "checkoutOomRollout"   # add this to src/flagd/demo.flagd.json
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
