// 신규 계정 정보를 검증해 서버에 등록하고 로그인 화면으로 연결하는 파일입니다.
import 'package:flutter/material.dart';

import 'services/auth_api_service.dart';
import 'widgets/app_back_button.dart';

/// 닉네임·이메일·비밀번호를 입력받는 회원가입 폼 화면입니다.
class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key, this.authApiService});

  /// 이메일 로그인 화면에서 진입했음을 알리는 경로 인자입니다.
  /// 이 값이 전달되면 로그인 화면을 새로 쌓지 않고 pop으로 되돌아갑니다.
  static const String fromEmailLoginArgument = 'from-email-login';

  final AuthApiService? authApiService;

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  final TextEditingController _nicknameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _confirmPasswordController =
      TextEditingController();
  late final AuthApiService _authApiService;

  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  @override
  void initState() {
    super.initState();
    _authApiService = widget.authApiService ?? AuthApiService();
  }

  @override
  void dispose() {
    _nicknameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  // 각 입력값의 필수 여부와 최소 형식, 비밀번호 일치 여부를 검사합니다.
  String? _validateNickname(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '닉네임을 입력해 주세요';
    }

    if (text.length < 2) {
      return '닉네임은 2자 이상 입력해 주세요';
    }

    return null;
  }

  String? _validateEmail(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '이메일을 입력해 주세요';
    }

    if (!text.contains('@') || !text.contains('.')) {
      return '올바른 이메일 형식을 입력해 주세요';
    }

    return null;
  }

  // 서버에는 입력값을 그대로 보내므로 검증도 trim 없이 같은 값으로 수행합니다.
  String? _validatePassword(String? value) {
    final text = value ?? '';

    if (text.trim().isEmpty) {
      return '비밀번호를 입력해 주세요';
    }

    if (text != text.trim()) {
      return '비밀번호 앞뒤 공백은 사용할 수 없어요';
    }

    if (text.length < 8) {
      return '비밀번호는 8자 이상 입력해 주세요';
    }

    return null;
  }

  String? _validateConfirmPassword(String? value) {
    final text = value ?? '';

    if (text.trim().isEmpty) {
      return '비밀번호 확인을 입력해 주세요';
    }

    if (text != _passwordController.text) {
      return '비밀번호가 일치하지 않습니다';
    }

    return null;
  }

  /// 이메일 로그인에서 진입했으면 pop으로 되돌아가 화면이 중복으로 쌓이지 않게 하고,
  /// 그 외 경로에서는 기존처럼 로그인 화면으로 교체 이동합니다.
  void _navigateBackToEmailLogin({String? email}) {
    final cameFromEmailLogin =
        ModalRoute.of(context)?.settings.arguments ==
        SignupScreen.fromEmailLoginArgument;

    if (cameFromEmailLogin && Navigator.canPop(context)) {
      Navigator.pop(context, email);
      return;
    }

    Navigator.pushReplacementNamed(context, '/email-login', arguments: email);
  }

  /// 폼이 유효할 때 가입 API를 호출하고, 성공하면 이메일을 로그인 화면에 전달합니다.
  Future<void> _handleSignup() async {
    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    final email = _emailController.text.trim();

    setState(() {
      _isLoading = true;
    });

    try {
      await _authApiService.signup(
        nickname: _nicknameController.text.trim(),
        email: email,
        password: _passwordController.text,
      );

      if (!mounted) return;

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('회원가입이 완료되었습니다. 로그인해 주세요.')));

      _navigateBackToEmailLogin(email: email);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.userMessage)));
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // 네 입력란이 같은 모양과 포커스·오류 스타일을 사용하도록 공통화했습니다.
  InputDecoration _inputDecoration({
    required String labelText,
    required String hintText,
    Widget? suffixIcon,
  }) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final fillColor = isDark
        ? const Color(0xFF1C1C1E)
        : const Color(0xFFF1F1F4);
    final hintColor = isDark
        ? const Color(0xFF9A9A9A)
        : const Color(0xFF9E9E9E);
    final enabledBorderColor = isDark
        ? const Color(0xFF2C2C2E)
        : Colors.transparent;

    return InputDecoration(
      labelText: labelText,
      hintText: hintText,
      labelStyle: TextStyle(color: hintColor, fontSize: 15),
      hintStyle: TextStyle(color: hintColor, fontSize: 15),
      filled: true,
      fillColor: fillColor,
      contentPadding: const EdgeInsets.symmetric(horizontal: 22, vertical: 22),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: BorderSide(
          color: enabledBorderColor,
          width: isDark ? 1 : 0,
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: const BorderSide(color: Color(0xFF4A4EFE), width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: const BorderSide(color: Colors.redAccent, width: 1.2),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(28),
        borderSide: const BorderSide(color: Colors.redAccent, width: 1.5),
      ),
      suffixIcon: suffixIcon,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);
    final iconColor = isDark
        ? const Color(0xFFB8B8BE)
        : const Color(0xFF8C8C8C);

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
          '회원가입',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: constraints.maxHeight - 12,
                  ),
                  child: IntrinsicHeight(
                    child: Column(
                      children: [
                        const SizedBox(height: 40),
                        Text(
                          'K-DPP 계정을 만들어보세요',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: primaryText,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Text(
                          '닉네임과 계정 정보를 입력하고 서비스를 시작해 보세요.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 14,
                            color: secondaryText,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 36),
                        TextFormField(
                          controller: _nicknameController,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.nickname],
                          validator: _validateNickname,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(
                            labelText: '닉네임',
                            hintText: '예: 홍길동',
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.email],
                          autocorrect: false,
                          validator: _validateEmail,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(
                            labelText: '이메일',
                            hintText: 'honggildong@example.com',
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _obscurePassword,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.newPassword],
                          enableSuggestions: false,
                          autocorrect: false,
                          validator: _validatePassword,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(
                            labelText: '비밀번호',
                            hintText: '8자 이상 입력',
                            suffixIcon: IconButton(
                              onPressed: () {
                                setState(() {
                                  _obscurePassword = !_obscurePassword;
                                });
                              },
                              tooltip: _obscurePassword
                                  ? '비밀번호 표시'
                                  : '비밀번호 숨기기',
                              icon: Icon(
                                _obscurePassword
                                    ? Icons.visibility_off_outlined
                                    : Icons.visibility_outlined,
                                color: iconColor,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _confirmPasswordController,
                          obscureText: _obscureConfirmPassword,
                          textInputAction: TextInputAction.done,
                          autofillHints: const [AutofillHints.newPassword],
                          enableSuggestions: false,
                          autocorrect: false,
                          validator: _validateConfirmPassword,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(
                            labelText: '비밀번호 확인',
                            hintText: '비밀번호 다시 입력',
                            suffixIcon: IconButton(
                              onPressed: () {
                                setState(() {
                                  _obscureConfirmPassword =
                                      !_obscureConfirmPassword;
                                });
                              },
                              tooltip: _obscureConfirmPassword
                                  ? '비밀번호 확인 표시'
                                  : '비밀번호 확인 숨기기',
                              icon: Icon(
                                _obscureConfirmPassword
                                    ? Icons.visibility_off_outlined
                                    : Icons.visibility_outlined,
                                color: iconColor,
                              ),
                            ),
                          ),
                          onFieldSubmitted: (_) {
                            if (!_isLoading) {
                              _handleSignup();
                            }
                          },
                        ),
                        const SizedBox(height: 32),
                        SizedBox(
                          width: double.infinity,
                          height: 60,
                          child: ElevatedButton(
                            onPressed: _isLoading ? null : _handleSignup,
                            style: ElevatedButton.styleFrom(
                              elevation: 0,
                              backgroundColor: const Color(0xFF4A4EFE),
                              disabledBackgroundColor: const Color(0x8C4A4EFE),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(30),
                              ),
                            ),
                            child: _isLoading
                                ? Semantics(
                                    label: '회원가입 처리 중',
                                    liveRegion: true,
                                    child: const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2.4,
                                        color: Colors.white,
                                      ),
                                    ),
                                  )
                                : const Text(
                                    '회원가입',
                                    style: TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w700,
                                      color: Colors.white,
                                    ),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 18),
                        TextButton(
                          onPressed: () => _navigateBackToEmailLogin(),
                          style: TextButton.styleFrom(
                            minimumSize: const Size(48, 48),
                          ),
                          child: Text(
                            '이미 계정이 있으신가요? 로그인',
                            style: TextStyle(
                              color: isDark
                                  ? const Color(0xFFB8B8BE)
                                  : const Color(0xFF5F6368),
                              fontSize: 14,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                        const Spacer(),
                        const SizedBox(height: 24),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
