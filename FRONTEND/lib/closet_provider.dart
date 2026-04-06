import 'package:flutter/material.dart';

class Clothes {
  final String title;
  final String category;
  final int health;
  final Map<String, dynamic> materials; // 백엔드 데이터와 호환을 위해 dynamic으로 변경!
  final String careInstruction;
  final double carbonFootprint;

  Clothes({
    required this.title,
    required this.category,
    required this.health,
    required this.materials,
    required this.careInstruction,
    required this.carbonFootprint,
  });
}

class ClosetProvider with ChangeNotifier {
  // 샘플 데이터들도 새로 바뀐 설계도에 맞춰 빈칸을 다 채워줍니다.
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

  List<Clothes> get items => _items;

  void addClothes(Clothes newClothes) {
    _items.add(newClothes);
    notifyListeners();
  }
}