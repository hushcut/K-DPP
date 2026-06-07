import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/closet_storage_service.dart';

class FakeClosetStorage implements ClosetStorage {
  List<Clothes>? _savedItems;
  final Map<String, List<Clothes>> _accountItems = {};
  String? _savedUserName;
  String? _savedUserEmail;

  @override
  Future<void> clearClothesList() async {
    _savedItems = null;
  }

  @override
  Future<void> clearClothesListFor(String ownerEmail) async {
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
  Future<List<Clothes>> loadClothesListFor(String ownerEmail) async {
    return List<Clothes>.from(_accountItems[_normalizeEmail(ownerEmail)] ?? []);
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
    _savedItems = List<Clothes>.from(items);
  }

  @override
  Future<void> saveClothesListFor(
    String ownerEmail,
    List<Clothes> items,
  ) async {
    _accountItems[_normalizeEmail(ownerEmail)] = List<Clothes>.from(items);
  }

  @override
  Future<void> saveUserName(String userName) async {
    _savedUserName = userName;
  }

  @override
  Future<void> saveUserEmail(String userEmail) async {
    _savedUserEmail = userEmail;
  }

  String _normalizeEmail(String value) {
    return value.trim().toLowerCase();
  }
}
