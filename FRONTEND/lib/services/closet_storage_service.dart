import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/closet_sort_option.dart';
import '../models/clothes.dart';

/// 옷장 목록과 사용자 이름·이메일·id·로그인 방법을 영구 저장하기 위한 추상 인터페이스다.
///
/// 계정별 옷장의 주인 키(`ownerKey`)는 이메일 계정이면 이메일, 이메일이 없는 계정(카카오)이면
/// `user:<서버 사용자 id>` 다(`ClosetProvider`). 이메일에는 늘 `@` 가 있어 두 키가 겹치지 않는다.
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

  /// 주인 키에 해당하는 계정별 옷장 데이터의 존재 여부를 확인한다.
  Future<bool> hasSavedClothesListFor(String ownerKey);
  /// 특정 계정의 옷장 목록을 저장한다.
  Future<void> saveClothesListFor(String ownerKey, List<Clothes> items);
  /// 특정 계정의 옷장 목록을 불러온다.
  Future<List<Clothes>> loadClothesListFor(String ownerKey);
  /// 특정 계정의 옷장 목록을 불러오되, 저장된 적이 없으면 null을 반환한다.
  Future<List<Clothes>?> loadClothesListOrNullFor(String ownerKey);
  /// 특정 계정의 옷장 목록을 삭제한다.
  Future<void> clearClothesListFor(String ownerKey);

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

  /// 마지막으로 사용한 서버 사용자 id 를 저장한다.
  Future<void> saveUserId(int userId);
  /// 저장된 사용자 id 를 불러온다.
  Future<int?> loadUserId();
  /// 저장된 사용자 id 를 삭제한다.
  Future<void> clearUserId();

  /// 마지막으로 사용한 계정의 로그인 방법(`user.login_methods`)을 저장한다.
  Future<void> saveLoginMethods(List<String> loginMethods);
  /// 저장된 로그인 방법을 불러온다. 저장된 적이 없으면(이 값을 저장하기 전 판의 로그인) null 이다.
  Future<List<String>?> loadLoginMethods();
  /// 저장된 로그인 방법을 삭제한다.
  Future<void> clearLoginMethods();

  /// 옷장 목록의 정렬 기준을 저장한다.
  Future<void> saveClosetSortOption(ClosetSortOption option);
  /// 저장된 정렬 기준을 불러온다. 저장된 값이 없으면 기본값을 반환한다.
  Future<ClosetSortOption> loadClosetSortOption();
}

/// [SharedPreferencesAsync]에 옷장 JSON과 사용자 이름·이메일·id·로그인 방법을 저장한다.
/// 계정별 키에는 주인 키 원문 대신 정규화 후 Base64 URL 인코딩한 값을 사용한다.
/// 누락되거나 손상된 옷장 JSON은 빈 목록으로 복구해 앱 시작 흐름을 유지한다.
class ClosetStorageService implements ClosetStorage {
  static const String _closetItemsKey = 'closet_items';
  static const String _accountClosetItemsKeyPrefix = 'closet_items_account_';
  static const String _userNameKey = 'user_name';
  static const String _userNameCustomizedKey = 'user_name_customized';
  static const String _userEmailKey = 'user_email';
  static const String _userIdKey = 'user_id';
  static const String _loginMethodsKey = 'user_login_methods';
  static const String _closetSortOptionKey = 'closet_sort_option';

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
  Future<bool> hasSavedClothesListFor(String ownerKey) async {
    final raw = await _prefs.getString(_accountClosetKey(ownerKey));
    return raw != null;
  }

  @override
  Future<void> saveClothesListFor(String ownerKey, List<Clothes> items) async {
    final encoded = jsonEncode(items.map((item) => item.toJson()).toList());

    await _prefs.setString(_accountClosetKey(ownerKey), encoded);
  }

  @override
  Future<List<Clothes>> loadClothesListFor(String ownerKey) async {
    final raw = await _prefs.getString(_accountClosetKey(ownerKey));
    return _decodeClothesList(raw);
  }

  @override
  Future<List<Clothes>?> loadClothesListOrNullFor(String ownerKey) async {
    final raw = await _prefs.getString(_accountClosetKey(ownerKey));
    if (raw == null) return null;
    return _decodeClothesList(raw);
  }

  @override
  Future<void> clearClothesListFor(String ownerKey) async {
    await _prefs.remove(_accountClosetKey(ownerKey));
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

  @override
  Future<void> saveUserId(int userId) async {
    await _prefs.setInt(_userIdKey, userId);
  }

  @override
  Future<int?> loadUserId() async {
    return _prefs.getInt(_userIdKey);
  }

  @override
  Future<void> clearUserId() async {
    await _prefs.remove(_userIdKey);
  }

  @override
  Future<void> saveLoginMethods(List<String> loginMethods) async {
    await _prefs.setStringList(_loginMethodsKey, loginMethods);
  }

  @override
  Future<List<String>?> loadLoginMethods() async {
    return _prefs.getStringList(_loginMethodsKey);
  }

  @override
  Future<void> clearLoginMethods() async {
    await _prefs.remove(_loginMethodsKey);
  }

  @override
  Future<void> saveClosetSortOption(ClosetSortOption option) async {
    await _prefs.setString(_closetSortOptionKey, option.storageValue);
  }

  @override
  Future<ClosetSortOption> loadClosetSortOption() async {
    return ClosetSortOption.fromStorage(
      await _prefs.getString(_closetSortOptionKey),
    );
  }

  String _accountClosetKey(String ownerKey) {
    final normalizedKey = ownerKey.trim().toLowerCase();
    final encodedKey = base64Url
        .encode(utf8.encode(normalizedKey))
        .replaceAll('=', '');
    return '$_accountClosetItemsKeyPrefix$encodedKey';
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
