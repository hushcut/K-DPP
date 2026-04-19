import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'models/clothes.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final closetProvider = context.watch<ClosetProvider>();
    final clothesCount = closetProvider.count;
    final totalCarbon = closetProvider.totalCarbonFootprint;
    final averageHealth = closetProvider.averageHealth;
    final latestItem = closetProvider.latestItem;
    final recentItems = _getRecentItems(closetProvider.items.toList());
    final userName = closetProvider.userName;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    final primaryText = isDark ? Colors.white : const Color(0xFF1A1A1A);
    final secondaryText =
    isDark ? const Color(0xFFD1D1D6) : Colors.grey;
    final cardColor =
    isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final cardBorderColor =
    isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
    final progressBackgroundColor =
    isDark ? const Color(0xFF2A2A2E) : Colors.grey.shade200;
    final tipShadowColor = isDark
        ? Colors.black.withValues(alpha: 0.18)
        : Colors.black.withValues(alpha: 0.02);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$userName님, 안녕하세요 👋',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: primaryText,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            clothesCount > 0
                ? '현재 옷장에 $clothesCount개의 의류가 등록되어 있어요.'
                : '아직 등록된 의류가 없어요. 스캔 탭에서 첫 의류를 등록해 보세요.',
            style: TextStyle(
              fontSize: 14,
              color: secondaryText,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 32),

          _buildCarbonDashboard(
            totalCarbon: totalCarbon,
            clothesCount: clothesCount,
          ),
          const SizedBox(height: 24),

          _buildCareTipCard(
            latestItem: latestItem,
            averageHealth: averageHealth,
            cardColor: cardColor,
            cardBorderColor: cardBorderColor,
            primaryText: primaryText,
            secondaryText: secondaryText,
            shadowColor: tipShadowColor,
            isDark: isDark,
          ),
          const SizedBox(height: 24),

          Text(
            '최근 등록한 의류 상태',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: primaryText,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '최근 등록된 의류의 상태와 관리 포인트를 확인해 보세요.',
            style: TextStyle(
              fontSize: 13,
              color: secondaryText,
            ),
          ),
          const SizedBox(height: 16),

          if (recentItems.isEmpty)
            _buildEmptyRecentCard(
              cardColor: cardColor,
              cardBorderColor: cardBorderColor,
              primaryText: primaryText,
              secondaryText: secondaryText,
            )
          else
            ...recentItems.map(
                  (item) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _buildLifeExpectancyCard(
                  title: item.title,
                  percentage: item.health,
                  subtitle: _buildHealthSubtitle(item),
                  cardColor: cardColor,
                  cardBorderColor: cardBorderColor,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  progressBackgroundColor: progressBackgroundColor,
                ),
              ),
            ),
        ],
      ),
    );
  }

  List<Clothes> _getRecentItems(List<Clothes> items) {
    final copied = List<Clothes>.from(items.reversed);
    return copied.take(2).toList();
  }

  Widget _buildCarbonDashboard({
    required double totalCarbon,
    required int clothesCount,
  }) {
    final savedTrees = totalCarbon <= 0 ? 0 : (totalCarbon / 6).ceil();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF4A4EFE),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4A4EFE).withValues(alpha: 0.30),
            blurRadius: 15,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '내 옷장 탄소 현황',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                totalCarbon.toStringAsFixed(1),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 36,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(width: 6),
              const Padding(
                padding: EdgeInsets.only(bottom: 4),
                child: Text(
                  'kg CO2eq',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            clothesCount > 0
                ? '등록된 의류 $clothesCount벌 기준으로 집계된 값입니다.'
                : '의류를 등록하면 탄소 현황이 자동으로 집계됩니다.',
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 13,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.20),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.park, color: Colors.white, size: 18),
                const SizedBox(width: 8),
                Text(
                  savedTrees > 0
                      ? '소나무 약 $savedTrees그루 규모와 비슷해요'
                      : '의류를 등록해 탄소 정보를 확인해 보세요',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCareTipCard({
    required Clothes? latestItem,
    required double averageHealth,
    required Color cardColor,
    required Color cardBorderColor,
    required Color primaryText,
    required Color secondaryText,
    required Color shadowColor,
    required bool isDark,
  }) {
    final String tipTitle;
    final String tipBody;
    final IconData iconData;
    final Color iconColor;
    final Color iconBgColor;

    if (latestItem == null) {
      tipTitle = '오늘의 관리 팁';
      tipBody = '새 의류를 등록하면 소재와 상태를 바탕으로 맞춤 관리 팁을 제공할 수 있어요.';
      iconData = Icons.tips_and_updates_outlined;
      iconColor = Colors.orange;
      iconBgColor =
      isDark ? const Color(0xFF3A2C1F) : Colors.orange.shade50;
    } else if (averageHealth < 40) {
      tipTitle = '의류 컨디션 점검이 필요해요';
      tipBody = '현재 평균 건강도가 낮아요. 건조기 사용을 줄이고 세탁 지침을 우선 확인해 주세요.';
      iconData = Icons.warning_amber_rounded;
      iconColor = Colors.redAccent;
      iconBgColor =
      isDark ? const Color(0xFF3A2222) : Colors.red.shade50;
    } else if (latestItem.materials.keys.any(
          (e) => e.toLowerCase().contains('cotton'),
    )) {
      tipTitle = '코튼 소재 관리 팁';
      tipBody =
      '${latestItem.title}은(는) 면 소재가 포함되어 있어요. 미지근한 물 세탁과 자연 건조가 잘 어울립니다.';
      iconData = Icons.local_laundry_service_outlined;
      iconColor = Colors.blue;
      iconBgColor =
      isDark ? const Color(0xFF1F3045) : Colors.blue.shade50;
    } else {
      tipTitle = '오늘의 관리 팁';
      tipBody =
      '${latestItem.title}의 세탁 지침을 기준으로 관리해 주세요. 라벨 정보를 따르면 의류 수명을 더 늘릴 수 있어요.';
      iconData = Icons.check_circle_outline;
      iconColor = Colors.green;
      iconBgColor =
      isDark ? const Color(0xFF1F3A2A) : Colors.green.shade50;
    }

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: cardBorderColor),
        boxShadow: [
          BoxShadow(
            color: shadowColor,
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: iconBgColor,
              shape: BoxShape.circle,
            ),
            child: Icon(iconData, color: iconColor),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  tipTitle,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                    color: primaryText,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  tipBody,
                  style: TextStyle(
                    color: secondaryText,
                    fontSize: 13,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyRecentCard({
    required Color cardColor,
    required Color cardBorderColor,
    required Color primaryText,
    required Color secondaryText,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: cardBorderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '아직 등록된 의류가 없습니다',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 15,
              color: primaryText,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            '스캔 탭에서 케어 라벨을 촬영하면 의류 상태와 관리 정보를 여기서 확인할 수 있어요.',
            style: TextStyle(
              color: secondaryText,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLifeExpectancyCard({
    required String title,
    required int percentage,
    required String subtitle,
    required Color cardColor,
    required Color cardBorderColor,
    required Color primaryText,
    required Color secondaryText,
    required Color progressBackgroundColor,
  }) {
    final Color statusColor =
    percentage > 70 ? Colors.green : (percentage > 40 ? Colors.orange : Colors.redAccent);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: cardBorderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                    color: primaryText,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '$percentage%',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: statusColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: percentage / 100,
              backgroundColor: progressBackgroundColor,
              color: statusColor,
              minHeight: 8,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            subtitle,
            style: TextStyle(
              color: secondaryText,
              fontSize: 12,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  String _buildHealthSubtitle(Clothes item) {
    if (item.health <= 20) {
      return '수명 만료에 가까워요. 재사용 또는 분리배출 방법을 함께 확인해 보세요.';
    }
    if (item.health <= 40) {
      return '관리 주의 단계예요. 세탁 빈도와 건조 방식을 점검해 주세요.';
    }
    if (item.health <= 70) {
      return '현재 상태는 보통이에요. 세탁 지침을 지키면 더 오래 입을 수 있어요.';
    }
    return '현재 상태가 좋아요. 지금의 관리 방식을 유지해 주세요.';
  }
}