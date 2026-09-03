// Concrete base for seismograph
// 300 x 300 x 300 mm block with 4 corner through-holes

// Parameters (edit as needed)
base_x = 300; // mm
base_y = 300; // mm
base_z = 300; // mm

hole_d = 8;       // hole diameter in mm (default 8 mm)
hole_offset = 20; // distance from each outer edge to hole center (mm)
hole_h = base_z + 10; // hole height to ensure full through-hole

$fn = 64; // cylinder resolution

module concrete_base() {
    difference() {
        // Centered cube
        cube([base_x, base_y, base_z], center=true);

        // Four corner holes (through along Z)
        x_off = (base_x/2) - hole_offset;
        y_off = (base_y/2) - hole_offset;

        translate([ x_off,  y_off, 0])    cylinder(h=hole_h, r=hole_d/2, center=true);
        translate([-x_off,  y_off, 0])    cylinder(h=hole_h, r=hole_d/2, center=true);
        translate([ x_off, -y_off, 0])    cylinder(h=hole_h, r=hole_d/2, center=true);
        translate([-x_off, -y_off,0])    cylinder(h=hole_h, r=hole_d/2, center=true);
    }
}

// Render the base
concrete_base();

// Notes:
// - Hole diameter and offset can be changed above.
// - To export STL: in OpenSCAD: Design -> Compile, then File -> Export -> Export as STL.
