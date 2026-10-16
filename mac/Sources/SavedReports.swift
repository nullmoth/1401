import Foundation
import Darwin

enum SavedReports {
    struct Failure: LocalizedError {
        let errorDescription: String?
        init(_ message: String) { errorDescription = message }
    }

    private static func openDirectory(_ url: URL, create: Bool = true) throws -> Int32 {
        var path = url.path
        if path == "/var" || path.hasPrefix("/var/") { path = "/private" + path }
        if path == "/tmp" || path.hasPrefix("/tmp/") { path = "/private" + path }
        let parts = path.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        guard path.hasPrefix("/"), path.utf8.count <= 4096, parts.count <= 64,
              !parts.isEmpty, parts.allSatisfy({ $0 != "." && $0 != ".." && !$0.contains("\0") }) else {
            throw Failure("The report folder path is invalid.")
        }
        var fd = open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw Failure("Could not open the report folder root.") }
        do {
            for part in parts {
                if create && mkdirat(fd, part, 0o700) != 0 && errno != EEXIST {
                    throw Failure("Could not create the report folder (\(errno)).")
                }
                let next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
                guard next >= 0 else { throw Failure("The report folder contains an unavailable or linked parent.") }
                close(fd); fd = next
            }
            var info = stat()
            guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFDIR,
                  info.st_uid == getuid(), info.st_mode & 0o077 == 0 else {
                throw Failure("The report folder is not a private folder owned by this account.")
            }
            return fd
        } catch { close(fd); throw error }
    }

    static func directory(_ url: URL) throws { let fd = try openDirectory(url); close(fd) }

    static func session(in parent: URL) throws -> URL {
        let fd = try openDirectory(parent)
        defer { close(fd) }
        let name = "report-" + UUID().uuidString
        guard mkdirat(fd, name, 0o700) == 0 else { throw Failure("Could not create a report folder (\(errno)).") }
        return parent.appendingPathComponent(name, isDirectory: true)
    }

    static func create(_ data: Data, in directory: URL, name: String) throws -> URL {
        guard !name.isEmpty, name != ".", name != "..", !name.contains("\0"), !name.contains("/"), !name.contains("\\") else {
            throw Failure("The report filename is invalid.")
        }
        let dir = try openDirectory(directory)
        defer { close(dir) }
        var info = stat()
        guard fstat(dir, &info) == 0, info.st_uid == getuid(), info.st_mode & 0o077 == 0 else {
            throw Failure("The report folder changed before saving.")
        }
        let fd = openat(dir, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw Failure("Could not create the report (\(errno)).") }
        var complete = false
        defer { close(fd); if !complete { unlinkat(dir, name, 0) } }
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let written = Darwin.write(fd, bytes.baseAddress!.advanced(by: offset), bytes.count - offset)
                if written < 0 && errno == EINTR { continue }
                guard written > 0 else { throw Failure("Could not save the report (\(errno)).") }
                offset += written
            }
        }
        guard fsync(fd) == 0 else { throw Failure("Could not finish saving the report (\(errno)).") }
        complete = true
        return directory.appendingPathComponent(name)
    }

    static func append(_ data: Data, to url: URL) throws {
        let parent = try openDirectory(url.deletingLastPathComponent())
        defer { close(parent) }
        let fd = openat(parent, url.lastPathComponent, O_WRONLY | O_APPEND | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw Failure("Could not open the saved report (\(errno)).") }
        defer { close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_uid == getuid(), info.st_mode & 0o077 == 0, info.st_nlink == 1 else {
            throw Failure("The saved report is not a private regular file owned by this account.")
        }
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let count = Darwin.write(fd, bytes.baseAddress!.advanced(by: offset), bytes.count - offset)
                if count < 0 && errno == EINTR { continue }
                guard count > 0 else { throw Failure("Could not append to the report (\(errno)).") }
                offset += count
            }
        }
        guard fsync(fd) == 0 else { throw Failure("Could not finish saving report output (\(errno)).") }
    }

    static func read(_ url: URL, maximum: Int, requirePrivate: Bool = true) throws -> Data {
        let parent = try openDirectory(url.deletingLastPathComponent(), create: false)
        defer { close(parent) }
        let fd = openat(parent, url.lastPathComponent, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw Failure("Could not read the saved report.") }
        defer { close(fd) }
        var before = stat()
        guard fstat(fd, &before) == 0, before.st_mode & S_IFMT == S_IFREG,
              before.st_uid == getuid(), before.st_nlink == 1,
              (!requirePrivate || before.st_mode & 0o077 == 0),
              before.st_size >= 0, before.st_size <= maximum else {
            throw Failure("The report file is unavailable, linked, oversized or has unsafe ownership.")
        }
        var bytes = Data(), buffer = [UInt8](repeating: 0, count: 32768)
        while true {
            let count = Darwin.read(fd, &buffer, buffer.count)
            if count < 0 && errno == EINTR { continue }
            guard count >= 0, bytes.count <= maximum - count else { throw Failure("The report exceeded its read limit.") }
            if count == 0 { break }
            bytes.append(contentsOf: buffer.prefix(count))
        }
        var after = stat()
        guard fstat(fd, &after) == 0, before.st_size == after.st_size, bytes.count == before.st_size,
              before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
              before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec,
              before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec,
              before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec else { throw Failure("The report changed while reading.") }
        return bytes
    }

    static func importCollection(_ text: String, to directory: URL) throws -> [String] {
        guard text.utf8.count <= 40 * 1024 * 1024 else { throw Failure("The collector response exceeded its limit.") }
        var seen = Set<String>(), warnings: [String] = []
        var status: Int?, warningCount = 0, retained = false
        let reasons: [String: String] = [
            "copy-failed": "Collected output could not be copied for export.",
            "stat-failed": "A collected file could not be measured.",
            "read-failed": "A collected file could not be read for export.",
            "encode-failed": "Collected output could not be encoded for export.",
            "invalid-file": "A collected filename or file type was refused.",
            "cleanup-failed": "Private collection cleanup could not finish."
        ]
        for line in text.replacingOccurrences(of: "\r", with: "\n").split(separator: "\n") {
            guard status == nil else { throw Failure("The collector returned records after completion.") }
            let parts = line.split(separator: " ", omittingEmptySubsequences: false)
            if parts.count == 2, parts[0] == "NMCOLLECT_STATUS" {
                let token = String(parts[1])
                guard token.range(of: #"^(0|[1-9][0-9]{0,2})$"#, options: .regularExpression) != nil,
                      let value = Int(token), value <= 255 else { throw Failure("The collector returned an invalid completion status.") }
                status = value; continue
            }
            if parts.count == 2, parts[0] == "NMCOLLECT_RETAINED" {
                let path = String(parts[1])
                guard !retained, warningCount < 64, path.utf8.count <= 200,
                      path.utf8.allSatisfy({ $0 >= 32 && $0 < 127 }),
                      path.range(of: #"^/private/var/root/1401-(logs|operation)\.[A-Za-z0-9]{8,64}$"#, options: .regularExpression) != nil else {
                    throw Failure("The collector returned an invalid retained-file location.")
                }
                retained = true; warningCount += 1
                warnings.append("Private diagnostic files remain at " + path + ".")
                continue
            }
            if parts.count == 2, parts[0] == "NMCOLLECT_WARNING", let reason = reasons[String(parts[1])] {
                guard warningCount < 64 else { throw Failure("The collector warning limit was exceeded.") }
                warningCount += 1; warnings.append(reason); continue
            }
            if parts.count == 2, parts[0] == "NMCOLLECT_TRUNCATED" {
                let token = String(parts[1])
                guard warningCount < 64,
                      token == "file-count" || token.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$"#, options: .regularExpression) != nil else {
                    throw Failure("The collector returned an invalid limit warning.")
                }
                warningCount += 1
                warnings.append(token + ": the collector reached its size or file limit."); continue
            }
            guard parts.count == 3, parts[0] == "NMCOLLECT_FILE" else { throw Failure("The collector returned an invalid record.") }
            let name = String(parts[1])
            guard name.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$"#, options: .regularExpression) != nil,
                  seen.count < 49, seen.insert(name).inserted,
                  let bytes = Data(base64Encoded: String(parts[2])), !bytes.isEmpty, bytes.count <= 524288 else {
                throw Failure("The collector returned an invalid file.")
            }
            _ = try create(bytes, in: directory, name: name)
        }
        guard let status else { throw Failure("The collector did not return its completion status.") }
        if status != 0 { warnings.append("System log collection did not complete (status \(status)); saved files remain available.") }
        if retained && status == 0 { throw Failure("The collector reported success while retaining failed export files.") }
        return warnings
    }
}

final class ReportUploadResult: @unchecked Sendable {
    private let lock = NSLock()
    private var result: (String?, String?)?
    func finish(data: Data?, response: URLResponse?, error: Error?, sha256: String) {
        let outcome: (String?, String?)
        if let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
           let data = data, let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let id = value["id"] as? String, !id.isEmpty, value["sha256"] as? String == sha256 {
            outcome = (id, nil)
        } else {
            outcome = (nil, error?.localizedDescription ?? "The server did not confirm the report bytes.")
        }
        lock.lock(); defer { lock.unlock() }
        if result == nil { result = outcome }
    }
    func take(timedOut: Bool) -> (String?, String?) {
        lock.lock(); defer { lock.unlock() }
        if timedOut { return (nil, "Upload timed out. The local report is retained.") }
        return result ?? (nil, "The upload did not finish. The local report is retained.")
    }
}
