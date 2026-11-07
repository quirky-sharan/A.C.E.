//! The per-run IPC token handed to each core process (§5.5, §5.6, D-50): 256 bits from the OS
//! random generator (`getrandom` -> `ProcessPrng` on Windows), written as 64 hex characters.

pub const TOKEN_BYTES: usize = 32;

pub fn new_token() -> Result<String, getrandom::Error> {
    let mut bytes = [0u8; TOKEN_BYTES];
    getrandom::fill(&mut bytes)?;
    Ok(to_hex(&bytes))
}

fn to_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(char::from(DIGITS[usize::from(byte >> 4)]));
        out.push(char::from(DIGITS[usize::from(byte & 0x0f)]));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tokens_are_64_lowercase_hex_characters_and_unique() {
        let first = new_token().unwrap();
        let second = new_token().unwrap();
        assert_eq!(first.len(), 2 * TOKEN_BYTES);
        assert!(
            first
                .chars()
                .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c))
        );
        assert_ne!(first, second);
    }

    #[test]
    fn hex_encoding() {
        assert_eq!(to_hex(&[0x00, 0x0f, 0xab, 0xff]), "000fabff");
    }
}
