#include "postgres.h"

int
time_in(char *timestr)
{
	if (timestr[0] == ':')
	{
		return 1;
	}
	return 0;
}

static int
time_parse(char *timestr, int *tzp)
{
	if (tzp == NULL)
	{
		return -1;
	}
	return 0;
}

int
timetz_in(char *timestr)
{
	int tz = 0;

	return time_parse(timestr, &tz);
}

int
time_in_other(char *timestr)
{
	int tz = 0;

	return time_parse(timestr, &tz);
}
