using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;
namespace A1401 {
    static class ScanEvidenceCheck {
        static int Main(string[] args) {
            bool ok = ScanEvidence.Verify();
            File.WriteAllText(args[0], new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                { "ok", ok }, { "scan_evidence_binding", ok }, { "network", false }, { "disk_writes", "temporary fixture directory only" } }));
            return ok ? 0 : 1;
        }
    }
}
