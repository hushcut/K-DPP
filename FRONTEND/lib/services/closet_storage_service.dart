import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/clothes.dart';

abstract class ClosetStorage {
  Future<bool> hasSavedClothesList();
  Future<void> saveClothesList(List<Clothes> items);
  Future<List<Clothes>> loadClothesList();
  Future<void> clearClothesList();

  Future<void> saveUserName(String userName);
  Future<String?> loadUserName();
  Future<void> clearUserName();
}

class ClosetStorageService implements ClosetStorage {
  static const String _closetItemsKey = 'closet_items';
  static const String _userNameKey = 'user_name';

  final SharedPreferencesAsync _prefs = SharedPreferencesAsync();

  @override
  Future<bool> hasSavedClothesList() async {
    final raw = await _prefs.getString(_closetItemsKey);
    return raw != null;
  }

  @override
  Future<void> saveClothesList(List<Clothes> items) async {
    final encoded = jsonEncode(
      items.map((item) => item.toJson()).toList(),
    );

    await _prefs.setString(_closetItemsKey, encoded);
  }

  @override
  Future<List<Clothes>> loadClothesList() async {
    final raw = await _prefs.getString(_closetItemsKey);

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

  @override
  Future<void> clearClothesList() async {
    await _prefs.remove(_closetItemsKey);
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
}