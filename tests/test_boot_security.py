import unittest
from types import SimpleNamespace
from p1401 import bootfix

class BootSecurity(unittest.TestCase):
    def apply(self, model, loading, log=True):
        cfg={'Misc':{'Security':{'SecureBootModel':model,'DmgLoading':loading}}}
        changes=[]
        bootfix.apply(cfg,SimpleNamespace(hardware={'CPU':{'Manufacturer':'Intel'}}),
                      ['OC: Cannot use Secure Boot with Any DmgLoading!'] if log else [],
                      lambda *args:changes.append(args))
        return cfg['Misc']['Security'],changes
    def test_conflict_requires_signed_recovery_preserves_enabled_model(self):
        for model in ('Default','j137','j185'):
            security,changes=self.apply(model,'Any')
            self.assertEqual(security,{'SecureBootModel':model,'DmgLoading':'Signed'})
            self.assertEqual(len(changes),1)
    def test_already_signed_no_extra_mutation(self):
        security,changes=self.apply('Default','Signed');self.assertFalse(changes)
        self.assertEqual(security['SecureBootModel'],'Default')
    def test_explicitly_disabled_model_is_not_overridden(self):
        security,changes=self.apply('Disabled','Any');self.assertFalse(changes)
        self.assertEqual(security,{'SecureBootModel':'Disabled','DmgLoading':'Any'})
    def test_without_matching_failure_no_security_change(self):
        security,changes=self.apply('Default','Any',False);self.assertFalse(changes)
        self.assertEqual(security,{'SecureBootModel':'Default','DmgLoading':'Any'})
