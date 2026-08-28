// 로그인과 회원가입 진입점을 제공하는 인증 시작 화면입니다.
import 'package:flutter/material.dart';

import 'theme/app_palette.dart';
import 'widgets/kdpp_logo_mark.dart';

/// 서비스 소개와 함께 이메일 로그인·회원가입 화면으로 이동하는 버튼을 표시합니다.
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final backgroundColor = palette.background;
    final primaryText = isDark ? Colors.white : const Color(0xFF1A1A1A);
    final secondaryText = palette.textSecondary;
    final subText = isDark ? const Color(0xFFB8B8BE) : const Color(0xFF5F6368);

    return Scaffold(
      backgroundColor: backgroundColor,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: IntrinsicHeight(
                  child: Column(
                    children: [
                      const Spacer(flex: 2),
                      const KdppLogoMark(size: 96, borderRadius: 28),
                      const SizedBox(height: 24),
                      Text(
                        'K-DPP',
                        style: TextStyle(
                          fontSize: 30,
                          fontWeight: FontWeight.bold,
                          color: primaryText,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        '의류를 더 오래, 더 바르게 관리하세요',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 16,
                          color: secondaryText,
                          height: 1.5,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '라벨 스캔으로 의류 상태와 관리 정보를\n쉽게 확인할 수 있어요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 14,
                          color: secondaryText,
                          height: 1.5,
                        ),
                      ),
                      const Spacer(flex: 3),
                      Padding(
                        padding: const EdgeInsets.only(bottom: 28),
                        child: Column(
                          children: [
                            SizedBox(
                              width: double.infinity,
                              height: 56,
                              child: ElevatedButton(
                                onPressed: () {
                                  Navigator.pushNamed(context, '/email-login');
                                },
                                style: ElevatedButton.styleFrom(
                                  elevation: 0,
                                  backgroundColor: AppPalette.accent,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                ),
                                child: const Text(
                                  '로그인',
                                  style: TextStyle(
                                    fontSize: 16,
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(height: 10),
                            TextButton(
                              onPressed: () {
                                Navigator.pushNamed(context, '/signup');
                              },
                              style: TextButton.styleFrom(
                                minimumSize: const Size(48, 48),
                              ),
                              child: Text(
                                '계정이 없으신가요? 회원가입',
                                style: TextStyle(
                                  fontSize: 14,
                                  color: subText,
                                  decoration: TextDecoration.underline,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
