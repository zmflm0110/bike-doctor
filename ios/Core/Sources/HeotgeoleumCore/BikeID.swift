import Foundation

public enum BikeID {
    /// 'spb 69683', 'SPB69683', 'SPB-69683' → 'SPB-69683'. 번호가 없으면 nil. (웹앱 lookup·서버 norm_bike 와 같은 규칙)
    public static func normalize(_ raw: String) -> String? {
        let up = raw.uppercased()
        guard let r = up.range(of: #"SPB-?\s?(\d{3,6})"#, options: .regularExpression) else { return nil }
        let digits = up[r].filter(\.isNumber)
        return "SPB-" + String(repeating: "0", count: max(0, 5 - digits.count)) + digits
    }

    /// 카메라 글자 인식(기기 안 AI)으로 읽은 한 덩어리 → 자전거 번호. 'SPB' 가 보이면 그대로, 아니면 숫자 5자리 한 덩어리만
    /// (대여소 번호·전화번호 같은 다른 숫자를 잘못 잡지 않게 — 4자리 이하·7자리 이상, 숫자 사이 다른 글자는 안 받음)
    public static func fromScan(_ text: String) -> String? {
        if let id = normalize(text) { return id }
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count == 5, t.allSatisfy(\.isASCII), t.allSatisfy(\.isNumber) else { return nil }
        return "SPB-" + t
    }
}
