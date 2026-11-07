//! Overlay geometry (§14.1, §14.2, D-55): where the orb and the sidebar go on a monitor's work area
//! (the screen minus the taskbar), and whether the cursor is over one of the UI's hit rectangles.
//! Rectangles are physical pixels; sizes are logical pixels scaled by the monitor's scale factor.

use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

impl Rect {
    pub fn contains(&self, x: i32, y: i32) -> bool {
        x >= self.x && x < self.x + self.width && y >= self.y && y < self.y + self.height
    }
}

/// A rectangle reported by the UI: CSS pixels from the window's top-left corner.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct CssRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Edge {
    #[default]
    Right,
    Left,
}

/// The orb window: the 56 px orb plus room for its glow (logical pixels).
pub const ORB_WINDOW: f64 = 72.0;
/// Gap between the orb window and the screen edge.
pub const ORB_MARGIN: f64 = 4.0;
/// The sidebar window: the 380 px panel plus 8 px for its glow on each side.
pub const SIDEBAR_WIDTH: f64 = 396.0;
/// Gap between the sidebar window and the screen edge, top and bottom.
pub const SIDEBAR_MARGIN: f64 = 8.0;

fn px(logical: f64, scale: f64) -> i32 {
    (logical * scale).round() as i32
}

/// The orb window at `edge` of `work`; `orb_y` runs from 0 (top) to 1 (bottom).
pub fn orb_rect(work: Rect, scale: f64, edge: Edge, orb_y: f64) -> Rect {
    let size = px(ORB_WINDOW, scale).min(work.width).min(work.height);
    let margin = px(ORB_MARGIN, scale);
    let x = match edge {
        Edge::Right => work.x + work.width - margin - size,
        Edge::Left => work.x + margin,
    };
    let travel = (work.height - size).max(0);
    let y = work.y + (orb_y.clamp(0.0, 1.0) * f64::from(travel)).round() as i32;
    Rect {
        x,
        y,
        width: size,
        height: size,
    }
}

/// The `orb_y` that puts the orb's centre at screen height `center_y` (dragging along the edge).
pub fn orb_y_for(work: Rect, scale: f64, center_y: i32) -> f64 {
    let size = px(ORB_WINDOW, scale);
    let travel = (work.height - size).max(1);
    let top = center_y - size / 2 - work.y;
    (f64::from(top) / f64::from(travel)).clamp(0.0, 1.0)
}

/// The sidebar window: full work-area height minus margins, at `edge`.
pub fn sidebar_rect(work: Rect, scale: f64, edge: Edge) -> Rect {
    let width = px(SIDEBAR_WIDTH, scale).min(work.width);
    let margin = px(SIDEBAR_MARGIN, scale);
    let height = (work.height - 2 * margin).max(1);
    let x = match edge {
        Edge::Right => work.x + work.width - margin - width,
        Edge::Left => work.x + margin,
    };
    Rect {
        x,
        y: work.y + margin,
        width,
        height,
    }
}

/// Is the cursor (physical screen pixels) over one of `rects` of a window at `window`?
pub fn hit(cursor: (i32, i32), window: Rect, scale: f64, rects: &[CssRect]) -> bool {
    if !window.contains(cursor.0, cursor.1) || scale <= 0.0 {
        return false;
    }
    let local_x = f64::from(cursor.0 - window.x) / scale;
    let local_y = f64::from(cursor.1 - window.y) / scale;
    rects.iter().any(|rect| {
        local_x >= rect.x
            && local_x < rect.x + rect.width
            && local_y >= rect.y
            && local_y < rect.y + rect.height
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const LAPTOP: Rect = Rect {
        x: 0,
        y: 0,
        width: 1920,
        height: 1152,
    }; // 1920×1200 minus taskbar

    #[test]
    fn the_orb_docks_to_either_edge_and_scales() {
        let right = orb_rect(LAPTOP, 1.25, Edge::Right, 0.5);
        assert_eq!(
            right,
            Rect {
                x: 1825,
                y: 531,
                width: 90,
                height: 90
            }
        );
        let left = orb_rect(LAPTOP, 1.25, Edge::Left, 0.0);
        assert_eq!(
            left,
            Rect {
                x: 5,
                y: 0,
                width: 90,
                height: 90
            }
        );
        let bottom = orb_rect(LAPTOP, 1.0, Edge::Right, 7.0); // clamped
        assert_eq!(bottom.y + bottom.height, 1152);
    }

    #[test]
    fn the_orb_follows_the_monitor_it_is_on() {
        let second = Rect {
            x: 1920,
            y: -200,
            width: 2560,
            height: 1400,
        };
        let orb = orb_rect(second, 1.5, Edge::Right, 1.0);
        assert_eq!(
            orb,
            Rect {
                x: 1920 + 2560 - 6 - 108,
                y: -200 + 1400 - 108,
                width: 108,
                height: 108
            }
        );
        assert!(second.contains(orb.x, orb.y));
    }

    #[test]
    fn dragging_maps_back_to_the_same_position() {
        for orb_y in [0.0, 0.25, 0.5, 1.0] {
            let rect = orb_rect(LAPTOP, 1.25, Edge::Right, orb_y);
            let again = orb_y_for(LAPTOP, 1.25, rect.y + rect.height / 2);
            assert!((again - orb_y).abs() < 0.01, "{orb_y} -> {again}");
        }
        assert_eq!(orb_y_for(LAPTOP, 1.0, -500), 0.0);
        assert_eq!(orb_y_for(LAPTOP, 1.0, 99_999), 1.0);
    }

    #[test]
    fn the_sidebar_fills_the_height_at_the_edge() {
        let work = Rect {
            x: 0,
            y: 0,
            width: 1920,
            height: 1040,
        };
        assert_eq!(
            sidebar_rect(work, 1.0, Edge::Right),
            Rect {
                x: 1516,
                y: 8,
                width: 396,
                height: 1024
            }
        );
        assert_eq!(sidebar_rect(work, 1.0, Edge::Left).x, 8);
        let narrow = Rect {
            x: 0,
            y: 0,
            width: 300,
            height: 600,
        };
        assert_eq!(sidebar_rect(narrow, 1.0, Edge::Right).width, 300);
    }

    #[test]
    fn hit_testing_uses_css_pixels_inside_the_window() {
        let window = Rect {
            x: 100,
            y: 100,
            width: 90,
            height: 90,
        }; // 72 logical px at 125 %
        let orb = [CssRect {
            x: 8.0,
            y: 8.0,
            width: 56.0,
            height: 56.0,
        }];
        assert!(hit((111, 111), window, 1.25, &orb)); // 8.8 css px in
        assert!(!hit((105, 105), window, 1.25, &orb)); // 4 css px in: the glow, click-through
        assert!(!hit((500, 500), window, 1.25, &orb)); // outside the window
        assert!(!hit((111, 111), window, 1.25, &[])); // nothing reported yet: all click-through
    }
}
