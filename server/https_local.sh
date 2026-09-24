#!/bin/sh
# 집 와이파이 안에서만 https — 아이폰 사파리는 https 가 아니면 위치·카메라(QR)를 막는다.
# 인터넷에 공개하지 않는다(맥 서버를 같은 와이파이의 아이폰만 봄). 만든 뒤 할 일은 맨 아래 안내.
#
# 안전장치: 인증서를 서명하는 '작은 인증기관' 키는 서버 인증서 하나를 서명한 직후 지운다
#   → 아이폰에 이 인증기관을 믿게 해도, 이 맥 서버 말고 다른 사이트 인증서는 누구도 새로 만들 수 없다.
#   게다가 이름 제약(.local 과 사설 IP 만)을 걸어 두었다.
set -e
cd "$(dirname "$0")/.."
OUT=data/tls
HOST="$(scutil --get LocalHostName).local"
IP="$(ipconfig getifaddr en0 || true)"
mkdir -p "$OUT"
cd "$OUT"
rm -f ca.key ca.crt server.key server.csr server.crt ca.srl

cat > ca.cnf <<CNF
[req]
distinguished_name = dn
prompt = no
x509_extensions = v3_ca
[dn]
CN = Heotgeoreum Zero local CA ($HOST)
[v3_ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
nameConstraints = critical, permitted;DNS:.local, permitted;DNS:localhost, permitted;IP:192.168.0.0/255.255.0.0, permitted;IP:10.0.0.0/255.0.0.0, permitted;IP:172.16.0.0/255.240.0.0, permitted;IP:127.0.0.0/255.0.0.0
CNF
cat > server.cnf <<CNF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = $HOST
[v3]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:$HOST, DNS:localhost, IP:127.0.0.1${IP:+, IP:$IP}
authorityKeyIdentifier = keyid
CNF

openssl req -x509 -new -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 397 -config ca.cnf 2>/dev/null
openssl req -new -newkey rsa:2048 -nodes -keyout server.key -out server.csr -config server.cnf 2>/dev/null
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 397 -sha256 -extfile server.cnf -extensions v3 2>/dev/null
rm -f ca.key ca.srl server.csr          # 인증기관 키는 여기서 버린다
chmod 600 server.key

echo "만들었습니다: $OUT/server.crt (이름: $HOST${IP:+, $IP}), 인증기관 키는 지웠습니다."
echo
echo "아이폰에서 (한 번만):"
echo "  1) $OUT/ca.crt 를 AirDrop 으로 아이폰에 보내기 → 설정 > '프로파일이 다운로드됨' > 설치"
echo "  2) 설정 > 일반 > 정보 > 인증서 신뢰 설정 > 'Heotgeoreum Zero local CA' 켜기"
echo "  3) 맥에서: python server/app.py 8443 --https"
echo "  4) 아이폰 사파리: https://$HOST:8443  (같은 와이파이)"
echo "지우려면: 아이폰 설정 > 일반 > VPN 및 기기 관리 > 프로파일 삭제, 맥에서 rm -r $OUT"
