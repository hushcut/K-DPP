import 'dart:collection';
import 'package:flutter/foundation.dart';
import 'models/clothes.dart';

class ClosetProvider with ChangeNotifier {
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

  ClosetProvider() {
    if (_items.isNotEmpty) {
      _selectedClothes = _items.last;
    }
  }

  UnmodifiableListView<Clothes> get items => UnmodifiableListView(_items);

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

  void addClothes(Clothes newClothes) {
    _items.add(newClothes);
    _selectedClothes = newClothes;
    notifyListeners();
  }

  void selectClothes(Clothes clothes) {
    _selectedClothes = clothes;
    notifyListeners();
  }
}