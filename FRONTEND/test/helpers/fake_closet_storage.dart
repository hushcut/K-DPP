import 'package:k_dpp/models/closet_sort_option.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/closet_storage_service.dart';

class FakeClosetStorage implements ClosetStorage {
  List<Clothes>? _savedItems;
  final Map<String, List<Clothes>> _accountItems = {};
  String? _savedUserName;
  bool _savedUserNameCustomized = false;
  String? _savedUserEmail;
  int? _savedUserId;
  List<String>? _savedLoginMethods;

  /// 옷장 저장 실패를 흉내 낼 때 던질 오류입니다.
  Object? saveClothesError;

  /// 계정별 옷장 삭제 실패를 흉내 낼 때 던질 오류입니다.
  Object? clearClothesForError;

  /// 정렬 기준 저장 실패를 흉내 낼 때 던질 오류입니다.
  Object? saveSortOptionError;

  // 실제 저장소처럼 문자열로 보관해 storageValue/fromStorage 매핑까지 검증합니다.
  String? _savedSortOption;

  @override
  Future<void> clearClothesList() async {
    _savedItems = null;
  }

  @override
  Future<void> clearClothesListFor(String ownerKey) async {
    if (clearClothesForError case final error?) {
      throw error;
    }

    _accountItems.remove(_normalizeKey(ownerKey));
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
  Future<bool> hasSavedClothesListFor(String ownerKey) async {
    return _accountItems.containsKey(_normalizeKey(ownerKey));
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
  Future<List<Clothes>> loadClothesListFor(String ownerKey) async {
    return List<Clothes>.from(_accountItems[_normalizeKey(ownerKey)] ?? []);
  }

  @override
  Future<List<Clothes>?> loadClothesListOrNullFor(String ownerKey) async {
    final items = _accountItems[_normalizeKey(ownerKey)];
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
  Future<void> saveClothesListFor(String ownerKey, List<Clothes> items) async {
    if (saveClothesError case final error?) {
      throw error;
    }

    _accountItems[_normalizeKey(ownerKey)] = List<Clothes>.from(items);
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

  @override
  Future<void> saveUserId(int userId) async {
    _savedUserId = userId;
  }

  @override
  Future<int?> loadUserId() async {
    return _savedUserId;
  }

  @override
  Future<void> clearUserId() async {
    _savedUserId = null;
  }

  @override
  Future<void> saveLoginMethods(List<String> loginMethods) async {
    _savedLoginMethods = List<String>.from(loginMethods);
  }

  @override
  Future<List<String>?> loadLoginMethods() async {
    final methods = _savedLoginMethods;
    return methods == null ? null : List<String>.from(methods);
  }

  @override
  Future<void> clearLoginMethods() async {
    _savedLoginMethods = null;
  }

  @override
  Future<void> saveClosetSortOption(ClosetSortOption option) async {
    if (saveSortOptionError case final error?) {
      throw error;
    }

    _savedSortOption = option.storageValue;
  }

  @override
  Future<ClosetSortOption> loadClosetSortOption() async {
    return ClosetSortOption.fromStorage(_savedSortOption);
  }

  /// 저장된 원시 문자열입니다. enum 이름이 아니라 storageValue가 기록됐는지 확인할 때 씁니다.
  String? get savedSortOptionRaw => _savedSortOption;

  /// 계정별 옷장이 저장된 주인 키들입니다. 키 형식에 기대지 않고 저장·삭제 여부만 볼 때 씁니다.
  Iterable<String> get savedAccountKeys => _accountItems.keys;

  String _normalizeKey(String value) {
    return value.trim().toLowerCase();
  }
}
