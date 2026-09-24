import Foundation

public enum BikeID {
    /// 'spb 69683', 'SPB69683', 'SPB-69683' → 'SPB-69683'. 번호가 없으면 nil. (웹앱 lookup·서버 norm_bike 와 같은 규칙)
    public static func normalize(_ raw: String) -> String? {
        let up = raw.uppercased()
        guard let r = up.range(of: #"SPB-?\s?(\d{3,6})"#, options: .regularExpression) else { return nil }
        let digits = up[r].filter(\.isNumber)
        return "SPB-" + String(repeating: "0", count: max(0, 5 - digits.count)) + digits
    }
}
