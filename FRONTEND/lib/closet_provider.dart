import 'dart:collection';
import 'package:flutter/foundation.dart';
import 'models/clothes.dart';
import 'services/closet_storage_service.dart';

class ClosetProvider with ChangeNotifier {
  final ClosetStorage _storageService;

  final List<Clothes> _items = [
    Clothes(
      title: '오가닉 코튼 맨투맨',
      category: '상의',
      health: 65,
      materials: {'cotton': 100},
      careInstruction: '30도 이하 물에서 세탁하세요.',
      carbonFootprint: 15.5,
    ),
    Clothes(
      title: '오래된 데님 팬츠',
      category: '하의',
      health: 10,
      materials: {'cotton': 98, 'polyurethane': 2},
      careInstruction: '단독 세탁 권장',
      carbonFootprint: 25.0,
    ),
  ];

  Clothes? _selectedClothes;
  bool _isLoaded = false;

  ClosetProvider({ClosetStorage? storage})
      : _storageService = storage ?? ClosetStorageService() {
    if (_items.isNotEmpty) {
      _selectedClothes = _items.last;
    }
  }

  UnmodifiableListView<Clothes> get items => UnmodifiableListView(_items);

  bool get isLoaded => _isLoaded;

  int get count => _items.length;

  Clothes? get latestItem => _items.isEmpty ? null : _items.last;

  Clothes? get selectedClothes => _selectedClothes;

  Clothes? get currentReportItem => _selectedClothes ?? latestItem;

  double get totalCarbonFootprint {
    return _items.fold(0.0, (sum, item) => sum + item.carbonFootprint);
  }

  double get averageHealth {
    if (_items.isEmpty) return 0.0;
    final total = _items.fold<int>(0, (sum, item) => sum + item.health);
    return total / _items.length;
  }

  Future<void> loadFromStorage() async {
    final hasSavedData = await _storageService.hasSavedClothesList();
    final savedItems = await _storageService.loadClothesList();

    if (hasSavedData) {
      _items
        ..clear()
        ..addAll(savedItems);
    }

    _selectedClothes = _items.isNotEmpty ? _items.last : null;
    _isLoaded = true;
    notifyListeners();
  }

  Future<void> _persist() async {
    await _storageService.saveClothesList(_items);
  }

  Future<void> addClothes(Clothes newClothes) async {
    _items.add(newClothes);
    _selectedClothes = newClothes;
    notifyListeners();
    await _persist();
  }

  void selectClothes(Clothes clothes) {
    _selectedClothes = clothes;
    notifyListeners();
  }

  Future<void> removeClothes(Clothes target) async {
    _items.remove(target);

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes == target) {
      _selectedClothes = _items.last;
    }

    notifyListeners();
    await _persist();
  }

  Future<void> removeClothesBatch(List<Clothes> targets) async {
    final targetSet = targets.toSet();
    _items.removeWhere((item) => targetSet.contains(item));

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes != null && targetSet.contains(_selectedClothes)) {
      _selectedClothes = _items.last;
    }

    notifyListeners();
    await _persist();
  }

  Future<void> setCustomOrder(List<Clothes> newOrder) async {
    _items
      ..clear()
      ..addAll(newOrder);

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes != null && !_items.contains(_selectedClothes)) {
      _selectedClothes = _items.last;
    }

    notifyListeners();
    await _persist();
  }

  Future<void> clearAllClothes() async {
    _items.clear();
    _selectedClothes = null;
    notifyListeners();
    await _storageService.clearClothesList();
  }
}