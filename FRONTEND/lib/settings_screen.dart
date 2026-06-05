import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'services/auth_api_service.dart';
import 'theme_provider.dart';
import 'widgets/app_back_button.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  static const String _devEmail = 'honggildong@kdpp.com';

  String _themeModeLabel(ThemeMode mode) {
    switch (mode) {
      case ThemeMode.dark:
        return '블랙';
      case ThemeMode.light:
        return '화이트';
      case ThemeMode.system:
        return '시스템 설정';
    }
  }

  Future<void> _editNickname(BuildContext context, String currentName) async {
    final controller = TextEditingController(text: currentName);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final result = await showDialog<String>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('닉네임 수정'),
          content: TextField(
            controller: controller,
            autofocus: true,
            style: TextStyle(
              color: isDark ? Colors.white : const Color(0xFF111111),
            ),
            decoration: InputDecoration(
              hintText: '예: 홍길동',
              hintStyle: TextStyle(
                color: isDark
                    ? const Color(0xFF9A9A9A)
                    : const Color(0xFF8C8C8C),
              ),
              filled: true,
              fillColor: isDark
                  ? const Color(0xFF2A2A2E)
                  : const Color(0xFFF1F1F4),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 18,
                vertical: 16,
              ),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(18),
                borderSide: BorderSide.none,
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('취소'),
            ),
            ElevatedButton(
              onPressed: () {
                Navigator.pop(dialogContext, controller.text.trim());
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF4A4EFE),
              ),
              child: const Text('저장', style: TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );

    if (result == null || result.trim().isEmpty) return;

    if (!context.mounted) return;

    await context.read<ClosetProvider>().setUserName(result);

    if (!context.mounted) return;

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('닉네임이 변경되었습니다.')));
  }

  Future<void> _confirmLogout(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('로그아웃'),
          content: const Text('로그아웃 하시겠어요?', style: TextStyle(height: 1.5)),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('취소'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF4A4EFE),
              ),
              child: const Text('로그아웃', style: TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    if (!context.mounted) return;

    try {
      await const AuthApiService().logout();
    } catch (_) {
      // 로컬 로그아웃은 서버 연결 여부와 관계없이 계속 진행합니다.
    }

    if (!context.mounted) return;

    await context.read<ClosetProvider>().logout();

    if (!context.mounted) return;

    Navigator.pushNamedAndRemoveUntil(context, '/login', (route) => false);
  }

  void _showComingSoon(BuildContext context, String title) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: Text(title),
          content: const Text(
            '이 기능은 다음 단계에서 추가할 예정입니다.',
            style: TextStyle(height: 1.5),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('확인'),
            ),
          ],
        );
      },
    );
  }

  Widget _buildSectionTitle(String title, Color color) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 10),
      child: Text(
        title,
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }

  Widget _buildMenuTile({
    required IconData icon,
    required String title,
    String? subtitle,
    Color iconColor = const Color(0xFF4A4EFE),
    Color textColor = const Color(0xFF111111),
    Color subtitleColor = const Color(0xFF8C8C8C),
    VoidCallback? onTap,
    bool showChevron = true,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 6),
      minLeadingWidth: 20,
      leading: Icon(icon, color: iconColor, size: 22),
      title: Text(
        title,
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: textColor,
        ),
      ),
      subtitle: subtitle == null
          ? null
          : Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                subtitle,
                style: TextStyle(
                  fontSize: 13,
                  color: subtitleColor,
                  height: 1.4,
                ),
              ),
            ),
      trailing: showChevron
          ? Icon(Icons.chevron_right, color: subtitleColor)
          : null,
      onTap: onTap,
    );
  }

  Widget _buildCard(List<Widget> children, Color background, Color border) {
    return Container(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: border),
      ),
      child: Column(children: children),
    );
  }

  @override
  Widget build(BuildContext context) {
    final userName = context.watch<ClosetProvider>().userName;
    final themeMode = context.watch<ThemeProvider>().themeMode;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark
        ? const Color(0xFF2C2C2E)
        : const Color(0xFFEAEAEA);
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);
    final sectionText = isDark
        ? const Color(0xFF9A9A9A)
        : const Color(0xFF8E8E93);
    final profileBoxColor = isDark
        ? const Color(0xFF2A2A2E)
        : const Color(0xFFEEF1FF);

    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: AppBar(
        backgroundColor: backgroundColor,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        automaticallyImplyLeading: false,
        leadingWidth: 52,
        leading: const Padding(
          padding: EdgeInsets.only(left: 8),
          child: AppBackButton(),
        ),
        title: Text(
          '설정',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        children: [
          Container(
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              color: cardColor,
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: borderColor),
            ),
            child: Row(
              children: [
                Container(
                  width: 62,
                  height: 62,
                  decoration: BoxDecoration(
                    color: profileBoxColor,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(
                    Icons.person_outline,
                    color: Color(0xFF4A4EFE),
                    size: 30,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        userName,
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: primaryText,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        _devEmail,
                        style: TextStyle(fontSize: 14, color: secondaryText),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 28),

          _buildSectionTitle('내 정보', sectionText),
          _buildCard(
            [
              _buildMenuTile(
                icon: Icons.person_outline,
                title: '닉네임',
                subtitle: userName,
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () => _editNickname(context, userName),
              ),
              Divider(height: 1, color: borderColor),
              _buildMenuTile(
                icon: Icons.mail_outline,
                title: '이메일',
                subtitle: _devEmail,
                textColor: primaryText,
                subtitleColor: secondaryText,
                showChevron: false,
              ),
            ],
            cardColor,
            borderColor,
          ),
          const SizedBox(height: 24),

          _buildSectionTitle('앱 설정', sectionText),
          _buildCard(
            [
              _buildMenuTile(
                icon: Icons.dark_mode_outlined,
                title: '화면 설정',
                subtitle: _themeModeLabel(themeMode),
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () {
                  Navigator.pushNamed(context, '/display-settings');
                },
              ),
            ],
            cardColor,
            borderColor,
          ),
          const SizedBox(height: 24),

          _buildSectionTitle('계정 관리', sectionText),
          _buildCard(
            [
              _buildMenuTile(
                icon: Icons.lock_outline,
                title: '비밀번호 변경',
                subtitle: '비밀번호를 다시 설정합니다.',
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () => _showComingSoon(context, '비밀번호 변경'),
              ),
              Divider(height: 1, color: borderColor),
              _buildMenuTile(
                icon: Icons.logout,
                title: '로그아웃',
                subtitle: '현재 계정에서 로그아웃합니다.',
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () => _confirmLogout(context),
              ),
              Divider(height: 1, color: borderColor),
              _buildMenuTile(
                icon: Icons.person_remove_outlined,
                title: '회원 탈퇴',
                subtitle: '계정을 삭제합니다.',
                iconColor: Colors.redAccent,
                textColor: Colors.redAccent,
                subtitleColor: secondaryText,
                onTap: () => _showComingSoon(context, '회원 탈퇴'),
              ),
            ],
            cardColor,
            borderColor,
          ),
        ],
      ),
    );
  }
}
