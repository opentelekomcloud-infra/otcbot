use serde::Deserialize;
use std::collections::HashMap;

#[derive(Clone, Debug, Deserialize)]
pub struct Config {
    pub matrix: Matrix,
    pub registry: Registry,
    pub store_path: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Matrix {
    pub homeserver: String,
    pub username: String,
    pub password: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Registry {
    pub username: Option<String>,
    // password: Option<String>,
    pub images: HashMap<String, ImageConfig>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ImageConfig {
    pub upstream: String,
    pub downstream: String,
}

impl Config {
    pub fn from_config_file(config_file: &str) -> Self {
        let f = std::fs::File::open(config_file).expect("Could not open file.");
        let config: Config = serde_yaml::from_reader(f).expect("Could not read values.");
        println!("Config is {:?}", config);
        return config;
    }
}

#[cfg(test)]
mod test {
    use super::*;

    // #[test]
    // fn test_config() {
    //     let config = Config::from_config_file("");
    //     //assert_eq!("a", &flag.name);
    // }
}
