import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/clothes.dart';

abstract class ClosetStorage {
  Future<bool> hasSavedClothesList();
  Future<void> saveClothesList(List<Clothes> items);
  Future<List<Clothes>> loadClothesList();
  Future<void> clearClothesList();

  Future<bool> hasSavedClothesListFor(String ownerEmail);
  Future<void> saveClothesListFor(String ownerEmail, List<Clothes> items);
  Future<List<Clothes>> loadClothesListFor(String ownerEmail);
  Future<void> clearClothesListFor(String ownerEmail);

  Future<void> saveUserName(String userName);
  Future<String?> loadUserName();
  Future<void> clearUserName();

  Future<void> saveUserEmail(String userEmail);
  Future<String?> loadUserEmail();
  Future<void> clearUserEmail();
}

class ClosetStorageService implements ClosetStorage {
  static const String _closetItemsKey = 'closet_items';
  static const String _accountClosetItemsKeyPrefix = 'closet_items_account_';
  static const String _userNameKey = 'user_name';
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
