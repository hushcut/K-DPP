import 'package:flutter/material.dart';

import 'services/auth_api_service.dart';
import 'widgets/app_back_button.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key, this.authApiService});

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
    _authApiService = widget.authApiService ?? const AuthApiService();
  }

  @override
  void dispose() {
    _nicknameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

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

  String? _validatePassword(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '비밀번호를 입력해 주세요';
    }

    if (text.length < 8) {
      return '비밀번호는 8자 이상 입력해 주세요';
    }

    return null;
  }

  String? _validateConfirmPassword(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '비밀번호 확인을 입력해 주세요';
    }

    if (text != _passwordController.text.trim()) {
      return '비밀번호가 일치하지 않습니다';
    }

    return null;
  }

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

      Navigator.pushReplacementNamed(context, '/email-login', arguments: email);
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

  InputDecoration _inputDecoration({
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
      hintText: hintText,
      hintStyle: TextStyle(color: hintColor, fontSize: 16),
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
                          validator: _validateNickname,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(
                            hintText: '닉네임 (예: 홍길동)',
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          validator: _validateEmail,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(hintText: '이메일'),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _obscurePassword,
                          validator: _validatePassword,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(
                            hintText: '비밀번호',
                            suffixIcon: IconButton(
                              onPressed: () {
                                setState(() {
                                  _obscurePassword = !_obscurePassword;
                                });
                              },
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
                          validator: _validateConfirmPassword,
                          style: TextStyle(color: primaryText),
                          cursorColor: const Color(0xFF4A4EFE),
                          decoration: _inputDecoration(
                            hintText: '비밀번호 확인',
                            suffixIcon: IconButton(
                              onPressed: () {
                                setState(() {
                                  _obscureConfirmPassword =
                                      !_obscureConfirmPassword;
                                });
                              },
                              icon: Icon(
                                _obscureConfirmPassword
                                    ? Icons.visibility_off_outlined
                                    : Icons.visibility_outlined,
                                color: iconColor,
                              ),
                            ),
                          ),
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
                                ? const SizedBox(
                                    width: 22,
                                    height: 22,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2.4,
                                      color: Colors.white,
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
                          onPressed: () {
                            Navigator.pushReplacementNamed(
                              context,
                              '/email-login',
                            );
                          },
                          child: Text(
                            '이미 계정이 있으신가요? 로그인',
                            style: TextStyle(
                              color: isDark
                                  ? const Color(0xFFB8B8BE)
                                  : const Color(0xFF9A9A9A),
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
