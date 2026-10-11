// Webcam clip adapter for a 2020 T-slot extrusion boom.
// Defaults are an unmeasured test fit. Set the dimensions after measuring the
// webcam's folding clip and checking the boom position over the keyboard.

plate_width = 85;       // width of the flat edge held by the webcam clip
plate_height = 48;      // exposed vertical height above the base
plate_thickness = 6;    // thickness the webcam clip grips
base_depth = 62;        // room for 2020 extrusion attachment behind plate
base_thickness = 7;
bolt_spacing = 28;      // two M5 T-nuts along the extrusion slot
slot_length = 9;        // adjustment parallel to the extrusion
bolt_clearance = 5.6;
rib_width = 7;

$fn = 48;

assert(plate_width >= 50);
assert(plate_thickness >= 4);
assert(base_depth > bolt_spacing + slot_length + 10);

module oblong_hole(length, diameter, height) {
    hull() {
        translate([0, -length / 2 + diameter / 2, 0])
            cylinder(h = height, d = diameter);
        translate([0, length / 2 - diameter / 2, 0])
            cylinder(h = height, d = diameter);
    }
}

difference() {
    union() {
        // Base sits against the underside of the extrusion. The webcam clips
        // over the top edge of the upright at the front of the base.
        translate([-plate_width / 2, 0, 0])
            cube([plate_width, base_depth, base_thickness]);
        translate([-plate_width / 2, 0, 0])
            cube([plate_width, plate_thickness, base_thickness + plate_height]);

        // Triangular buttresses reduce bending at the upright/base joint.
        for (x = [-plate_width / 3, plate_width / 3]) {
            hull() {
                translate([x - rib_width / 2, plate_thickness, base_thickness])
                    cube([rib_width, 1, 25]);
                translate([x - rib_width / 2, 28, base_thickness])
                    cube([rib_width, 1, 1]);
            }
        }
    }

    // M5 screws go upward into two T-nuts in one extrusion slot.
    for (y = [base_depth / 2 - bolt_spacing / 2,
              base_depth / 2 + bolt_spacing / 2]) {
        translate([0, y, -1])
            oblong_hole(slot_length, bolt_clearance, base_thickness + 2);
    }
}
