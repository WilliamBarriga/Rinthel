//! Cada sesión de porteo extrae acá su propio widget on-demand, en vez de
//! adivinar la abstracción correcta antes de que haga falta (ver
//! port-map.md). `log_tail` es el primero (sesión 01).

pub mod log_tail;
