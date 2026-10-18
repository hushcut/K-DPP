// 이 기기가 계정 옷장을 서버 백업과 마지막으로 맞춘 상태와, 옷장 내용의 지문을 만드는 파일입니다.
import 'dart:convert';

import 'clothes.dart';

/// 이 기기가 계정 옷장을 서버 백업(`/me/closet`)과 마지막으로 맞춘 상태입니다(DECISIONS 242).
///
/// [userId]·[apiBaseUrl] 이 지금 계정·서버와 다르면 '맞춘 적 없음'으로 봅니다([matches]).
/// [fingerprint] 는 서버 [version] 판 내용을 이 기기 표기([closetCanonicalJson])로 본 지문이라,
/// 지금 목록의 지문과 다르면 이 기기에서 옷장이 바뀐 것입니다.
class ClosetBackupState {
  const ClosetBackupState({
    required this.userId,
    required this.apiBaseUrl,
    required this.version,
    required this.fingerprint,
  });

  final int userId;
  final String apiBaseUrl;
  final int version;
  final String fingerprint;

  /// 지금 계정·서버와 맞춘 상태인지입니다.
  bool matches({required int userId, required String apiBaseUrl}) {
    return this.userId == userId && this.apiBaseUrl == apiBaseUrl;
  }

  /// 기기 저장소에 넣을 글자입니다.
  String encode() {
    return jsonEncode({
      'uid': userId,
      'api': apiBaseUrl,
      'v': version,
      'h': fingerprint,
    });
  }

  /// 저장된 글자를 읽습니다. 없거나 모양이 틀리면 null(맞춘 적 없음)입니다.
  static ClosetBackupState? tryDecode(String? raw) {
    if (raw == null) return null;

    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;

      final userId = decoded['uid'];
      final apiBaseUrl = decoded['api'];
      final version = decoded['v'];
      final fingerprint = decoded['h'];

      if (userId is! int ||
          apiBaseUrl is! String ||
          version is! int ||
          version < 0 ||
          fingerprint is! String) {
        return null;
      }

      return ClosetBackupState(
        userId: userId,
        apiBaseUrl: apiBaseUrl,
        version: version,
        fingerprint: fingerprint,
      );
    } on FormatException {
      return null;
    }
  }
}

/// 옷장 목록을 기기 저장소에 쓰는 글자와 똑같이 바꿉니다(`ClosetStorageService.saveClothesListFor`).
String closetCanonicalJson(List<Clothes> items) {
  return jsonEncode(items.map((item) => item.toJson()).toList());
}

/// 옷장 목록의 지문 `'<UTF-8 바이트 수>:<FNV-1a 64비트 16진수>'` 입니다.
///
/// `String.hashCode` 는 실행마다 같다는 보장이 없어 쓰지 않습니다 — 지문은 기기에 남아
/// 다음 실행의 목록과 견줍니다.
String closetFingerprint(List<Clothes> items) {
  return closetTextFingerprint(closetCanonicalJson(items));
}

/// 글자 하나의 지문입니다([closetFingerprint]).
String closetTextFingerprint(String text) {
  final bytes = utf8.encode(text);
  // 네이티브(iOS·Android)의 int 는 64비트라 곱셈이 2^64 로 감겨 FNV-1a 64비트가 그대로 나옵니다.
  var hash = 0xcbf29ce484222325;

  for (final byte in bytes) {
    hash ^= byte;
    hash *= 0x100000001b3;
  }

  final high = (hash >> 32) & 0xFFFFFFFF;
  final low = hash & 0xFFFFFFFF;
  final hex =
      high.toRadixString(16).padLeft(8, '0') +
      low.toRadixString(16).padLeft(8, '0');

  return '${bytes.length}:$hex';
}
