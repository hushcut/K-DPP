import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/clothes.dart';

/// 옷장 목록과 사용자 이름·이메일을 영구 저장하기 위한 추상 인터페이스다.
abstract class ClosetStorage {
  /// 계정과 연결되지 않은 옷장 데이터의 존재 여부를 확인한다.
  Future<bool> hasSavedClothesList();
  /// 계정과 연결되지 않은 옷장 목록을 저장한다.
  Future<void> saveClothesList(List<Clothes> items);
  /// 계정과 연결되지 않은 옷장 목록을 불러온다.
  Future<List<Clothes>> loadClothesList();
  /// 계정과 연결되지 않은 옷장 목록을 불러오되, 저장된 적이 없으면 null을 반환한다.
  Future<List<Clothes>?> loadClothesListOrNull();
  /// 계정과 연결되지 않은 옷장 목록을 삭제한다.
  Future<void> clearClothesList();

  /// 정규화된 이메일에 해당하는 계정별 옷장 데이터의 존재 여부를 확인한다.
  Future<bool> hasSavedClothesListFor(String ownerEmail);
  /// 특정 계정의 옷장 목록을 저장한다.
  Future<void> saveClothesListFor(String ownerEmail, List<Clothes> items);
  /// 특정 계정의 옷장 목록을 불러온다.
  Future<List<Clothes>> loadClothesListFor(String ownerEmail);
  /// 특정 계정의 옷장 목록을 불러오되, 저장된 적이 없으면 null을 반환한다.
  Future<List<Clothes>?> loadClothesListOrNullFor(String ownerEmail);
  /// 특정 계정의 옷장 목록을 삭제한다.
  Future<void> clearClothesListFor(String ownerEmail);

  /// 마지막으로 사용한 사용자 이름을 저장한다.
  Future<void> saveUserName(String userName);
  /// 저장된 사용자 이름을 불러온다.
  Future<String?> loadUserName();
  /// 저장된 사용자 이름을 삭제한다.
  Future<void> clearUserName();

  /// 사용자가 기기에서 직접 수정한 닉네임인지 여부를 저장한다.
  Future<void> saveUserNameCustomized(bool value);
  /// 닉네임 직접 수정 여부를 불러온다. 저장된 값이 없으면 false를 반환한다.
  Future<bool> loadUserNameCustomized();
  /// 닉네임 직접 수정 여부를 삭제한다.
  Future<void> clearUserNameCustomized();

  /// 마지막으로 사용한 사용자 이메일을 저장한다.
  Future<void> saveUserEmail(String userEmail);
  /// 저장된 사용자 이메일을 불러온다.
  Future<String?> loadUserEmail();
  /// 저장된 사용자 이메일을 삭제한다.
  Future<void> clearUserEmail();
}

/// [SharedPreferencesAsync]에 옷장 JSON과 사용자 이름·이메일을 저장한다.
/// 계정별 키에는 이메일 원문 대신 정규화 후 Base64 URL 인코딩한 값을 사용한다.
/// 누락되거나 손상된 옷장 JSON은 빈 목록으로 복구해 앱 시작 흐름을 유지한다.
class ClosetStorageService implements ClosetStorage {
  static const String _closetItemsKey = 'closet_items';
  static const String _accountClosetItemsKeyPrefix = 'closet_items_account_';
  static const String _userNameKey = 'user_name';
  static const String _userNameCustomizedKey = 'user_name_customized';
  static const String _userEmailKey = 'user_email';

  final SharedPreferencesAsync _prefs = SharedPreferencesAsync();

  @override
  Future<bool> hasSavedClothesList() async {
    final raw = await _prefs.getString(_closetItemsKey);
    return raw != null;
  }

  @override
  Future<void> saveClothesList(List<Clothes> items) async {
    final encoded = jsonEncode(items.map((item) => item.toJson()).toList());

    await _prefs.setString(_closetItemsKey, encoded);
  }

  @override
  Future<List<Clothes>> loadClothesList() async {
    final raw = await _prefs.getString(_closetItemsKey);
    return _decodeClothesList(raw);
  }

  @override
  Future<List<Clothes>?> loadClothesListOrNull() async {
    final raw = await _prefs.getString(_closetItemsKey);
    if (raw == null) return null;
    return _decodeClothesList(raw);
  }

  @override
  Future<void> clearClothesList() async {
    await _prefs.remove(_closetItemsKey);
  }

  @override
  Future<bool> hasSavedClothesListFor(String ownerEmail) async {
    final raw = await _prefs.getString(_accountClosetKey(ownerEmail));
    return raw != null;
  }

  @override
  Future<void> saveClothesListFor(
    String ownerEmail,
    List<Clothes> items,
  ) async {
    final encoded = jsonEncode(items.map((item) => item.toJson()).toList());

    await _prefs.setString(_accountClosetKey(ownerEmail), encoded);
  }

  @override
  Future<List<Clothes>> loadClothesListFor(String ownerEmail) async {
    final raw = await _prefs.getString(_accountClosetKey(ownerEmail));
    return _decodeClothesList(raw);
  }

  @override
  Future<List<Clothes>?> loadClothesListOrNullFor(String ownerEmail) async {
    final raw = await _prefs.getString(_accountClosetKey(ownerEmail));
    if (raw == null) return null;
    return _decodeClothesList(raw);
  }

  @override
  Future<void> clearClothesListFor(String ownerEmail) async {
    await _prefs.remove(_accountClosetKey(ownerEmail));
  }

  @override
  Future<void> saveUserName(String userName) async {
    await _prefs.setString(_userNameKey, userName);
  }

  @override
  Future<String?> loadUserName() async {
    return _prefs.getString(_userNameKey);
  }

  @override
  Future<void> clearUserName() async {
    await _prefs.remove(_userNameKey);
  }

  @override
  Future<void> saveUserNameCustomized(bool value) async {
    await _prefs.setBool(_userNameCustomizedKey, value);
  }

  @override
  Future<bool> loadUserNameCustomized() async {
    return await _prefs.getBool(_userNameCustomizedKey) ?? false;
  }

  @override
  Future<void> clearUserNameCustomized() async {
    await _prefs.remove(_userNameCustomizedKey);
  }

  @override
  Future<void> saveUserEmail(String userEmail) async {
    await _prefs.setString(_userEmailKey, userEmail);
  }

  @override
  Future<String?> loadUserEmail() async {
    return _prefs.getString(_userEmailKey);
  }

  @override
  Future<void> clearUserEmail() async {
    await _prefs.remove(_userEmailKey);
  }

  String _accountClosetKey(String ownerEmail) {
    final normalizedEmail = ownerEmail.trim().toLowerCase();
    final encodedEmail = base64Url
        .encode(utf8.encode(normalizedEmail))
        .replaceAll('=', '');
    return '$_accountClosetItemsKeyPrefix$encodedEmail';
  }

  List<Clothes> _decodeClothesList(String? raw) {
    if (raw == null || raw.isEmpty) {
      return [];
    }

    try {
      final decoded = jsonDecode(raw);

      if (decoded is! List) {
        return [];
      }

      return decoded
          .whereType<Map>()
          .map((item) => Clothes.fromJson(Map<String, dynamic>.from(item)))
          .toList();
    } catch (_) {
      return [];
    }
  }
}
