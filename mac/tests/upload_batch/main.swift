import Foundation

let batch = newUploadBatch()
var runs = Set<String>()
for _ in 0..<1024 {
    let value = newUploadBatch()
    assert(value.range(of: #"^1401-mac-[0-9a-f]{16}$"#, options: .regularExpression) != nil)
    assert(runs.insert(value).inserted)
}
for _ in 0..<3 {
    let data = try JSONSerialization.data(withJSONObject: ["consent": true, "batch": batch])
    let header = data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    var base64 = header.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
    while base64.count % 4 != 0 { base64 += "=" }
    let value = try JSONSerialization.jsonObject(with: Data(base64Encoded: base64)!) as! [String: Any]
    assert(value["batch"] as? String == batch)
}
assert(newUploadBatch() != batch)
print("Fresh anonymous upload runs are distinct; files in one send share one batch.")
