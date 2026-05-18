import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/clothes.dart';

enum ClosetSortOption {
  eco,
  health,
  latest,
}

class ClosetScreen extends StatefulWidget {
  const ClosetScreen({super.key});

  @override
  State<ClosetScreen> createState() => _ClosetScreenState();
}

class _ClosetScreenState extends State<ClosetScreen> {
  ClosetSortOption _sortOption = ClosetSortOption.eco;

  String get _sortLabel {
    switch (_sortOption) {
      case ClosetSortOption.eco:
        return '친환경 순';
      case ClosetSortOption.health:
        return '건강도 순';
      case ClosetSortOption.latest:
        return '최신 등록 순';
    }
  }

  List<Clothes> _sortClothes(List<Clothes> source, List<Clothes> originalOrder) {
    final sorted = List<Clothes>.from(source);

    switch (_sortOption) {
      case ClosetSortOption.eco:
        sorted.sort((a, b) => a.carbonFootprint.compareTo(b.carbonFootprint));
        break;

      case ClosetSortOption.health:
        sorted.sort((a, b) => b.health.compareTo(a.health));
        break;

      case ClosetSortOption.latest:
        final indexMap = <Clothes, int>{};
        for (int i = 0; i < originalOrder.length; i++) {
          indexMap[originalOrder[i]] = i;
        }

        sorted.sort((a, b) {
          final aIndex = indexMap[a] ?? 0;
          final bIndex = indexMap[b] ?? 0;
          return bIndex.compareTo(aIndex);
        });
        break;
    }

    return sorted;
  }

  @override
  Widget build(BuildContext context) {
    final clothesList = context.watch<ClosetProvider>().items;

    final allItems = _sortClothes(
      List<Clothes>.from(clothesList),
      clothesList.toList(),
    );

    final topItems = _sortClothes(
      clothesList.where((item) => item.category == '상의').toList(),
      clothesList.toList(),
    );

    final bottomItems = _sortClothes(
      clothesList.where((item) => item.category == '하의').toList(),
      clothesList.toList(),
    );

    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(20.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  '홍길동님의 옷장',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF1A1A1A),
                  ),
                ),
                PopupMenuButton<ClosetSortOption>(
                  onSelected: (value) {
                    setState(() {
                      _sortOption = value;
                    });
                  },
                  itemBuilder: (context) => const [
                    PopupMenuItem(
                      value: ClosetSortOption.eco,
                      child: Text('친환경 순'),
                    ),
                    PopupMenuItem(
                      value: ClosetSortOption.health,
                      child: Text('건강도 순'),
                    ),
                    PopupMenuItem(
                      value: ClosetSortOption.latest,
                      child: Text('최신 등록 순'),
                    ),
                  ],
                  child: OutlinedButton.icon(
                    onPressed: null,
                    icon: const Icon(Icons.sort, size: 18),
                    label: Text(_sortLabel),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF4A4EFE),
                      disabledForegroundColor: const Color(0xFF4A4EFE),
                      side: const BorderSide(color: Color(0xFF4A4EFE)),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const TabBar(
            labelColor: Color(0xFF4A4EFE),
            unselectedLabelColor: Colors.grey,
            indicatorColor: Color(0xFF4A4EFE),
            indicatorWeight: 3,
            tabs: [
              Tab(text: '전체'),
              Tab(text: '상의'),
              Tab(text: '하의'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                _buildClothesList(
                  context,
                  allItems,
                  emptyMessage: '옷장에 등록된 의류가 없습니다.',
                ),
                _buildClothesList(
                  context,
                  topItems,
                  emptyMessage: '상의 목록이 비어있습니다.',
                ),
                _buildClothesList(
                  context,
                  bottomItems,
                  emptyMessage: '하의 목록이 비어있습니다.',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildClothesList(
      BuildContext context,
      List<Clothes> clothes, {
        required String emptyMessage,
      }) {
    if (clothes.isEmpty) {
      return Center(
        child: Text(
          emptyMessage,
          style: const TextStyle(color: Colors.grey),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: clothes.length,
      itemBuilder: (context, index) {
        final item = clothes[index];

        return Padding(
          padding: const EdgeInsets.only(bottom: 12.0),
          child: _buildClosetItem(
            context,
            item: item,
            title: item.title,
            category: item.category,
            status: item.health > 20
                ? '건강 상태: ${item.health}%'
                : '수명 만료 (배출 권장)',
            statusColor: item.health > 20 ? Colors.green : Colors.redAccent,
            statusIcon: item.health > 20
                ? Icons.sentiment_satisfied_alt
                : Icons.warning_amber_rounded,
            isWarning: item.health <= 20,
          ),
        );
      },
    );
  }

  Widget _buildClosetItem(
      BuildContext context, {
        required Clothes item,
        required String title,
        required String category,
        required String status,
        required Color statusColor,
        required IconData statusIcon,
        bool isWarning = false,
      }) {
    return Container(
      decoration: BoxDecoration(
        color: isWarning ? Colors.red.shade50 : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isWarning ? Colors.redAccent.shade200 : Colors.grey.shade200,
          width: isWarning ? 2 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: Container(
          width: 60,
          height: 60,
          decoration: BoxDecoration(
            color: isWarning ? Colors.white : Colors.grey.shade100,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(
            Icons.checkroom,
            color: isWarning ? Colors.redAccent : Colors.grey,
            size: 30,
          ),
        ),
        title: Text(
          title,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 8.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                category,
                style: const TextStyle(
                  color: Colors.grey,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Icon(statusIcon, color: statusColor, size: 16),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      status,
                      style: TextStyle(
                        color: statusColor,
                        fontWeight:
                        isWarning ? FontWeight.bold : FontWeight.normal,
                        fontSize: 13,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        trailing: const Icon(Icons.chevron_right, color: Colors.grey),
        onTap: () {
          context.read<ClosetProvider>().selectClothes(item);
          Navigator.pushNamed(context, '/report', arguments: item);
        },
      ),
    );
  }
}