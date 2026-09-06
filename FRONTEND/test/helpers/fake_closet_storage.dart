import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/closet_storage_service.dart';

class FakeClosetStorage implements ClosetStorage {
  List<Clothes>? _savedItems;
  final Map<String, List<Clothes>> _accountItems = {};
  String? _savedUserName;
  bool _savedUserNameCustomized = false;
  String? _savedUserEmail;

  /// 옷장 저장 실패를 흉내 낼 때 던질 오류입니다.
  Object? saveClothesError;

  /// 계정별 옷장 삭제 실패를 흉내 낼 때 던질 오류입니다.
  Object? clearClothesForError;

  @override
  Future<void> clearClothesList() async {
    _savedItems = null;
  }

  @override
  Future<void> clearClothesListFor(String ownerEmail) async {
    if (clearClothesForError case final error?) {
      throw error;
    }

    _accountItems.remove(_normalizeEmail(ownerEmail));
  }

  @override
  Future<void> clearUserName() async {
    _savedUserName = null;
  }

  @override
  Future<void> clearUserEmail() async {
    _savedUserEmail = null;
  }

  @override
  Future<bool> hasSavedClothesList() async {
    return _savedItems != null;
  }

  @override
  Future<bool> hasSavedClothesListFor(String ownerEmail) async {
    return _accountItems.containsKey(_normalizeEmail(ownerEmail));
  }

  @override
  Future<List<Clothes>> loadClothesList() async {
    return List<Clothes>.from(_savedItems ?? []);
  }

  @override
  Future<List<Clothes>?> loadClothesListOrNull() async {
    final items = _savedItems;
    return items == null ? null : List<Clothes>.from(items);
  }

  @override
  Future<List<Clothes>> loadClothesListFor(String ownerEmail) async {
    return List<Clothes>.from(_accountItems[_normalizeEmail(ownerEmail)] ?? []);
  }

  @override
  Future<List<Clothes>?> loadClothesListOrNullFor(String ownerEmail) async {
    final items = _accountItems[_normalizeEmail(ownerEmail)];
    return items == null ? null : List<Clothes>.from(items);
  }

  @override
  Future<String?> loadUserName() async {
    return _savedUserName;
  }

  @override
  Future<String?> loadUserEmail() async {
    return _savedUserEmail;
  }

  @override
  Future<void> saveClothesList(List<Clothes> items) async {
    if (saveClothesError case final error?) {
      throw error;
    }

    _savedItems = List<Clothes>.from(items);
  }

  @override
  Future<void> saveClothesListFor(
    String ownerEmail,
    List<Clothes> items,
  ) async {
    if (saveClothesError case final error?) {
      throw error;
    }

    _accountItems[_normalizeEmail(ownerEmail)] = List<Clothes>.from(items);
  }

  @override
  Future<void> saveUserName(String userName) async {
    _savedUserName = userName;
  }

  @override
  Future<void> saveUserNameCustomized(bool value) async {
    _savedUserNameCustomized = value;
  }

  @override
  Future<bool> loadUserNameCustomized() async {
    return _savedUserNameCustomized;
  }

  @override
  Future<void> clearUserNameCustomized() async {
    _savedUserNameCustomized = false;
  }

  @override
  Future<void> saveUserEmail(String userEmail) async {
    _savedUserEmail = userEmail;
  }

  String _normalizeEmail(String value) {
    return value.trim().toLowerCase();
  }
}
