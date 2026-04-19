import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/closet_storage_service.dart';

class FakeClosetStorage implements ClosetStorage {
  List<Clothes>? _savedItems;
  String? _savedUserName;

  @override
  Future<void> clearClothesList() async {
    _savedItems = null;
  }

  @override
  Future<void> clearUserName() async {
    _savedUserName = null;
  }

  @override
  Future<bool> hasSavedClothesList() async {
    return _savedItems != null;
  }

  @override
  Future<List<Clothes>> loadClothesList() async {
    return List<Clothes>.from(_savedItems ?? []);
  }

  @override
  Future<String?> loadUserName() async {
    return _savedUserName;
  }

  @override
  Future<void> saveClothesList(List<Clothes> items) async {
    _savedItems = List<Clothes>.from(items);
  }

  @override
  Future<void> saveUserName(String userName) async {
    _savedUserName = userName;
  }
}