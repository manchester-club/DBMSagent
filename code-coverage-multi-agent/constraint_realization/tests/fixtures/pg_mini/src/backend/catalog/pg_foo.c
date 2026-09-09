#include "postgres.h"

List *
find_inheritance_children_extended(Oid parentrelId, bool omit_detached)
{
	HeapTuple inheritsTuple;

	if (((Form_pg_foo) GETSTRUCT(inheritsTuple))->foopend)
	{
		omit_detached = true;
	}
	return NIL;
}

bool
other_reader(HeapTuple tup)
{
	if (((Form_pg_foo) GETSTRUCT(tup))->barflag)
	{
		return true;
	}
	return false;
}
