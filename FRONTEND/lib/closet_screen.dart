import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';

class ClosetScreen extends StatelessWidget {
  const ClosetScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final clothesList = context.watch<ClosetProvider>().items;

    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(20.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('홍길동님의 옷장', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Color(0xFF1A1A1A))),
                OutlinedButton.icon(
                  onPressed: () {},
                  icon: const Icon(Icons.sort, size: 18),
                  label: const Text('친환경 순'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFF4A4EFE),
                    side: const BorderSide(color: Color(0xFF4A4EFE)),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
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
            tabs: [Tab(text: '전체'), Tab(text: '상의'), Tab(text: '하의')],
          ),
          Expanded(
            child: TabBarView(
              children: [
                ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: clothesList.length,
                  itemBuilder: (context, index) {
                    final item = clothesList[index];
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12.0),
                      child: _buildClosetItem(
                        context,
                        item: item, // 옷 데이터를 통째로 넘겨줍니다.
                        title: item.title,
                        category: item.category,
                        status: item.health > 20 ? '건강 상태: ${item.health}%' : '수명 만료 (배출 권장)',
                        statusColor: item.health > 20 ? Colors.green : Colors.redAccent,
                        statusIcon: item.health > 20 ? Icons.sentiment_satisfied_alt : Icons.warning_amber_rounded,
                        isWarning: item.health <= 20,
                      ),
                    );
                  },
                ),
                const Center(child: Text('상의 목록이 비어있습니다.', style: TextStyle(color: Colors.grey))),
                const Center(child: Text('하의 목록이 비어있습니다.', style: TextStyle(color: Colors.grey))),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildClosetItem(
      BuildContext context, {
        required Clothes item, // 여기서 데이터를 받아서
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
        border: Border.all(color: isWarning ? Colors.redAccent.shade200 : Colors.grey.shade200, width: isWarning ? 2 : 1),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.03), blurRadius: 10, offset: const Offset(0, 4))],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: Container(
          width: 60,
          height: 60,
          decoration: BoxDecoration(color: isWarning ? Colors.white : Colors.grey.shade100, borderRadius: BorderRadius.circular(12)),
          child: Icon(Icons.checkroom, color: isWarning ? Colors.redAccent : Colors.grey, size: 30),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 8.0),
          child: Row(
            children: [
              Icon(statusIcon, color: statusColor, size: 16),
              const SizedBox(width: 4),
              Expanded(child: Text(status, style: TextStyle(color: statusColor, fontWeight: isWarning ? FontWeight.bold : FontWeight.normal, fontSize: 13), overflow: TextOverflow.ellipsis)),
            ],
          ),
        ),
        trailing: const Icon(Icons.chevron_right, color: Colors.grey),
        onTap: () {
          // 🚀 👈 핵심 포인트! 리포트 화면으로 이동할 때 'item(옷 데이터 전체)'을 수화물(arguments)로 같이 보냅니다!
          Navigator.pushNamed(context, '/report', arguments: item);
        },
      ),
    );
  }
}